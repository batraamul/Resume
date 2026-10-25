# Template guide

A template is a versioned JSON specification that selects a **layout system** (header, headings, entries,
skills, columns, graphics) plus typography and colour. Content always comes from the resume mode and your
profile; templates never add text. Built-in templates live in `templates/`; your own copies live in the data
folder under `templates/` and can be created from *Resume Library → Templates → Duplicate…*.

## Built-in templates

| Template | Layout system | ATS-safe | Recommended modes |
|---|---|---|---|
| ATS Minimal | left header, plain headings, inline skills, single column, no tables | yes | ATS-optimised |
| Executive Technical | centred header, rule headings, title/date entries | no | One-page executive |
| Defence Technical | left header with thick rule, shaded headings, org-first entries | no | Defence & Intelligence |
| Scientific Research | small-caps headings, numbered publications | no | Scientific research CV |
| Engineering Professional | split header, caps-rule headings, skills table | no | Professional resume |
| AI/ML Specialist | left sidebar (contacts, skills, education), accent-bar headings | no | Technical specialist |
| Avionics & Drone Systems | navy banner header, stacked entries | no | Defence, Technical specialist |
| Government CV | numbered headings, bordered tables, particulars, declaration | no | Government bio-data |
| Modern Professional | margin labels | no | Professional |
| Academic Extended CV | date-left gutter entries | no | Academic CV |
| Compact Two-Page Resume | inline entries, tight spacing | no | Professional |
| Custom Diary Edition | diary palette | no | Professional |
| **Graphical Career Profile** | framed banner with icons, boxed summary, expertise table, timeline chart, right sidebar with competency bars | no | Graphical career profile |
| **Research Showcase** | metric tiles, publications-by-year chart, numbered papers, project cards, skill bars | no | Research portfolio |
| **Infographic Timeline** | banner with icons, left sidebar with bars, project cards, timeline chart | no | Project portfolio |

## Specification reference

```json
{
  "id": "user_my_template",            // lowercase, unique; user templates start with user_
  "name": "My template", "version": "1.0.0", "description": "…",
  "ats_safe": false, "tables_allowed": true, "recommended_modes": ["graphical_profile"],
  "summary_style": "plain | boxed | italic",
  "page":   {"margin_top_mm": 14, "margin_bottom_mm": 15, "margin_left_mm": 16, "margin_right_mm": 16},
  "fonts":  {"body": "Calibri", "heading": "Cambria", "name": "Cambria", "body_size": 10, "heading_size": 12,
             "name_size": 22, "headline_size": 11, "small_size": 8.8, "line_spacing": 1.08},
  "colours": {"text": "#1C2321", "muted": "#4D5955", "accent": "#145A47", "rule": "#9DB4AC", "fill": "#E6E9E8",
              "banner_fill": "#11806A", "banner_text": "#FFFFFF", "banner_outer": "#151A19",
              "sidebar_fill": "#F2F5F4", "link": "#145A47", "tile_fill": "#EAF2EF", "bar_track": "#CFDAD6"},
  "header":  {"style": "centered | left | split | banner | sidebar | framed", "name_case": "normal | upper | small_caps",
              "name_colour": "accent | text", "headline_colour": "accent | text | muted",
              "contact_style": "inline | stacked", "contact_icons": true, "separator": "  |  ",
              "rule": "none | single | double | thick"},
  "heading": {"style": "rule_below | caps_rule | shaded_bar | left_bar | small_caps | plain_bold | numbered | margin_label",
              "case": "upper | title | small_caps", "colour": "accent | text", "letter_spacing": 0.4,
              "space_before": 11, "space_after": 4, "rule_weight": 0.75, "label_width_mm": 32},
  "entry":   {"style": "title_date_right | org_first | stacked | date_left | inline", "date_style": "mon_year",
              "subtitle_italic": true, "bullet_glyph": "➢", "project_style": "standard | cards"},
  "skills":  {"style": "inline_categories | table | bullets | inline | bars", "competencies_style": "inline | columns | bullets"},
  "publications": {"style": "numbered | bulleted", "highlight_name": true},
  "columns": {"enabled": true, "side": "left | right", "width_frac": 0.31, "gap_mm": 6,
              "sidebar_sections": ["skills", "competencies", "training", "languages", "education"]},
  "graphics": {"enabled": true, "palette": ["#0F6E5C", "#2F4F1E", "#123E63"], "timeline_height_mm": 54,
               "chart_height_mm": 46, "tiles_per_row": 4, "bar_width_mm": 30},
  "footer":  {"page_numbers": "none | page_x_of_y | x_of_y | x", "show_name": true, "text": ""},
  "photo":   {"allowed": false, "width_mm": 28}
}
```

Fonts are limited to Calibri, Cambria, Arial and Times New Roman so pagination matches across Word,
LibreOffice and the built-in engine (which embeds metric-compatible open fonts).

## Rules enforced on load

* An **ATS-safe** template must have `tables_allowed: false`, no columns, a left or centred header,
  conventional headings, no skills table or bars, `graphics.enabled: false` and no project cards.
* A `sidebar` header requires columns; columns and `framed`/`banner` headers require `tables_allowed: true`.
* Colours must be `#RRGGBB`; sizes and margins have safe ranges. Invalid templates are skipped with a
  message, and a user template cannot reuse a built-in id.

## Graphics behaviour

* **Timeline** (`career_timeline` section): one bar per organisation, consecutive posts merged; height is
  years in post from your recorded dates; labels use each position's *Short organisation name*; the legend
  (colour square + organisation, posts, dates, highlight) is real text. Requires two or more dated positions.
* **Bars** (`skills.style: "bars"`): five steps from the skill's proficiency (Familiar 1 … Expert 5); unrated
  skills are listed as text. A note states that bars are self-assessed.
* **Tiles and chart** (`research_overview` section): counts by type and status, plus citations / h-index /
  i10-index with their source; a stacked publications-by-year chart appears with at least two years and
  three outputs.
* **Cards** (`entry.project_style: "cards"`): Challenge, Approach, Outcome, My contribution, verified
  metrics and technologies; only the approved external description when one exists.
* In templates without graphics, the same sections fall back to plain text (bullets or a single line).
* Inside two-column bodies, tables are not nested (paragraph versions are used) so LibreOffice and Word
  can split the columns across pages.

Every template change should increase `version`; saved resume versions record the template id and version,
and re-exports use the stored specification.
