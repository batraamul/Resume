"""PDF preview from in-memory bytes (nothing is written to disk for previews)."""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    HAVE_QTPDF = True
except ImportError:  # pragma: no cover - minimal Qt builds
    HAVE_QTPDF = False


class PdfPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.info = QLabel("No preview yet.")
        self.info.setObjectName("Muted")
        bar.addWidget(self.info, 1)
        self.prev = QToolButton()
        self.prev.setText("◀")
        self.prev.setAccessibleName("Previous page")
        self.next = QToolButton()
        self.next.setText("▶")
        self.next.setAccessibleName("Next page")
        self.page_label = QLabel("")
        self.zoom = QComboBox()
        self.zoom.setAccessibleName("Zoom")
        for text, val in (("Fit width", "width"), ("Whole page", "page"), ("75%", 0.75), ("100%", 1.0),
                          ("125%", 1.25), ("150%", 1.5)):
            self.zoom.addItem(text, val)
        bar.addWidget(self.prev)
        bar.addWidget(self.page_label)
        bar.addWidget(self.next)
        bar.addWidget(self.zoom)
        lay.addLayout(bar)
        self._buffer: QBuffer | None = None
        self._bytes = QByteArray()
        if HAVE_QTPDF:
            self.doc = QPdfDocument(self)
            self.view = QPdfView(self)
            self.view.setDocument(self.doc)
            self.view.setPageMode(QPdfView.PageMode.MultiPage)
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.view.setAccessibleName("Document preview")
            lay.addWidget(self.view, 1)
            nav = self.view.pageNavigator()
            self.prev.clicked.connect(lambda: self._jump(-1))
            self.next.clicked.connect(lambda: self._jump(1))
            nav.currentPageChanged.connect(lambda _p: self._update_page())
            self.zoom.currentIndexChanged.connect(self._zoom)
        else:  # pragma: no cover
            self.doc = None
            self.view = QLabel("Preview needs the Qt PDF module. Export the PDF and open it instead.")
            self.view.setWordWrap(True)
            lay.addWidget(self.view, 1)
        self.page_count = 0

    def _zoom(self) -> None:
        v = self.zoom.currentData()
        if v == "width":
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        elif v == "page":
            self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(float(v))

    def _jump(self, delta: int) -> None:
        nav = self.view.pageNavigator()
        p = min(max(nav.currentPage() + delta, 0), max(self.page_count - 1, 0))
        nav.jump(p, QPointF(), nav.currentZoom())

    def _update_page(self) -> None:
        if not HAVE_QTPDF:
            return
        cur = self.view.pageNavigator().currentPage() + 1 if self.page_count else 0
        self.page_label.setText(f"Page {cur} of {self.page_count}" if self.page_count else "")
        self.prev.setEnabled(cur > 1)
        self.next.setEnabled(cur < self.page_count)

    def set_pdf(self, data: bytes, info: str = "") -> None:
        if not HAVE_QTPDF:  # pragma: no cover
            self.info.setText(info)
            return
        self.doc.close()
        self._bytes = QByteArray(data)
        buf = QBuffer(self)
        buf.setData(self._bytes)
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        old = self._buffer
        self._buffer = buf
        self.doc.load(buf)
        if old is not None:
            old.close()
            old.deleteLater()
        self.page_count = self.doc.pageCount()
        self.info.setText(info)
        self._update_page()

    def clear(self, message: str = "No preview yet.") -> None:
        if HAVE_QTPDF:
            self.doc.close()
        self.page_count = 0
        self.info.setText(message)
        self._update_page()

    def status(self) -> int:
        return int(self.doc.status().value) if HAVE_QTPDF else -1


_ = Qt
