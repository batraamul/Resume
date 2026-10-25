# Research findings (October 2026) and how they shaped version 1.1

This note records what was researched online for version 1.1, the sources, and which feature each finding
became. Portal forms and recruitment rules change; the application shows the source next to every limit and
tells users to follow the official notification.

## 1. Applicant tracking systems (ATS)

| Finding | Feature |
|---|---|
| Use DOCX or a text-based PDF, never a scanned image or design-tool export. | *Job Portals → ATS check* fails PDFs without selectable text; exports are always text-based. |
| Single column; no tables, text boxes, columns or sidebars for core content. | ATS readiness check (`columns`, `tables`); graphical templates are flagged as not suited to portals; ATS-safe switch in the template designer enforces this. |
| Keep name and contact details in the body, not in page headers or footers. | All templates put contacts in the body; the check confirms it. |
| Leave out images, icons, logos, photos, charts and skill-rating bars. | `graphics` and `photo` checks; contact icons flagged. |
| Common fonts (Calibri, Arial, Georgia, Helvetica) at 10–12 pt; margins 0.5–1 inch; left-aligned text. | `font`, `font_size` and `margins` checks; template designer readability warnings. |
| Standard headings (Summary, Experience, Education, Skills); reverse-chronological order; consistent date format; plain round bullets. | `headings`, `chronology`, `dates` and `bullet_glyph` checks. |
| Mirror the posting's keywords (target about 75%), with full terms and acronyms. | `keywords` check against the vacancy analysis, listing missing terms "only where your records support them". |
| Summary of 3–4 sentences; 4–6 bullets for recent roles, 2–3 for older ones. | `summary`, `bullets_recent`, `bullets_older` checks. |

Source: [ATS resume format 2026 design guide (scale.jobs)](https://scale.jobs/blog/ats-resume-format-2026-design-guide).

AI screening is now common: in Deloitte India's *Campus Workforce Trends 2026* (27 August 2026), 86% of
organisations said AI is transforming hiring and 72% use it for resume screening. Source:
[Deloitte India press release](https://deloitte.com/in/en/about/press-room/india-s-campus-talent-landscape-pivots-to-skill-based-hiring-as-86-percent-of-employers-adopt-ai-in-recruitment--deloitte-india.html).
This is why ATS readiness is checked even though recruiters for government posts usually read documents
themselves.

## 2. Job portals

| Portal | Findings used | Sources |
|---|---|---|
| LinkedIn | Headline 220 characters; About 2,600 (only the first lines show before "see more"); experience description 2,000 per role; job title 100. Resume uploads DOC, DOCX or PDF; keep under 2 MB; four recent uploads are kept. Referrals and messages work better than one-click applications. | [Unilink LinkedIn limits 2026](https://unil.ink/blog/linkedin-character-limits-2026), [FastApply upload guide](https://blog.fastapply.co/how-to-upload-or-replace-resume-linkedin-indeed-naukri-2026), [Jobrise portal comparison](https://jobrise.io/blog/best-job-portals-india-2026) |
| Naukri.com | Upload DOC, DOCX, RTF or PDF up to 2 MB; one resume per profile; headline is a separate field; up to 50 key skills; headline under about 100 characters and a 200–300-word summary recommended; verify mobile and email, add a professional photo, fill every section. | [Naukri blog](https://www.naukri.com/blog/best-practices-for-your-naukri-profile), [FirstDay AI](https://firstdayai.in/blog/how-many-key-skills-can-you-add-on-naukri/), [Careerskraft](https://www.careerskraft.com/blog/naukri-profile-optimization-2026.html), [FastApply](https://blog.fastapply.co/how-to-upload-or-replace-resume-linkedin-indeed-naukri-2026) |
| Indeed | Resume can be public or private; uploading for one application does not make it public; only the latest file is kept. | [Indeed Help Centre](https://ca.indeed.com/help/job-seekers/articles/11314976176141-faqs-creating-uploading-and-managing-a-resume-file) |
| foundit, Instahyre, Shine, Hirist and others | Who each portal suits (experience level, sector); focus on two or three portals; tailor each application; follow up. | [Jobrise](https://jobrise.io/blog/best-job-portals-india-2026) |
| Government | National Career Service portal; Employment News for central government vacancies; notifications often prescribe their own format or file type. | [National Portal of India — NCS](https://services.india.gov.in/service/detail/national-career-service-job-search), [Jobrise PDF vs Word](https://jobrise.io/blog/resume-pdf-vs-word-format) |

File practice: name files like `Firstname_Lastname_Resume.pdf` (not `resume.pdf` or `final_v3`); keep portal
uploads under 2 MB and email attachments under about 1 MB. Source:
[Jobrise PDF vs Word](https://jobrise.io/blog/resume-pdf-vs-word-format).

**Features:** *Job Portals & Recruiters → Job portals* (guidance with sources), *Profile kit* (LinkedIn,
Naukri and Indeed text built from confirmed facts with live character/word counts), *ATS check → Check an
exported file* (type, size, selectable text, file name), new profile links (Naukri, Indeed, Scopus Author
ID, Web of Science ResearcherID alongside LinkedIn, GitHub, ORCID, Google Scholar and ResearchGate).

## 3. Recruiters and recruitment routes

| Finding | Source |
|---|---|
| DRDO direct recruitment of Scientist 'B' via GATE score and/or written test and interview through RAC (rac.gov.in); vacancies also in Employment News. | [MADE EASY](https://www.madeeasy.in/blog/must-know-facts-and-details-about-drdo-rac-recruitment), [RAC advertisement](https://www.drdo.gov.in/drdo/sites/default/files/career-vacancy-documents/advt153RAC03032025.pdf) |
| ISRO recruits Scientist/Engineer posts centrally through ICRB and through its centres' own notices. | [ISRO Current Opportunities](https://www.isro.gov.in/CurrentOpportunities.html) |
| Deputation applications use the DoPT bio-data proforma (OM 02.07.2015): service in chronological order, pay, nature of duties, additional qualifications and professional training, achievements, declaration, and the employer's certificate (vigilance, integrity, APARs for five years, penalties in ten years). | [CAG copy of the proforma](https://cag.gov.in/uploads/subsite_whats_new/Proforma-for-Biodata-as-per-DoPT-OM-dated-02-07-2015-06231703a0fb5a8-59987840.pdf) |

**Features:** *Recruiters* directory (routes, where vacancies are advertised, documents, interview focus,
official website, sources; one click creates a career target), dedicated training sections in the
Government CV (matching item 16(A) of the proforma), and the existing deputation bio-data mode.

## 4. Interview preparation and personal questionnaires

| Finding | Feature | Source |
|---|---|---|
| STAR: Situation ≈20%, Task ≈15%, Action ≈50%, Result ≈15%; answers of 60–90 seconds; say "I", not "we"; prepare 5–7 stories. | STAR story editor with a live check (shares, spoken length, I/we count, outcome); practice timer that turns amber after 90 seconds. | [The Interview Guys](https://blog.theinterviewguys.com/the-star-method/) |
| Boards draw most questions from the application form; say so when you do not know; do not over-elaborate; eye contact with every member; formal dress; the last 12 months of developments; stay calm on sensitive questions. | *Tips* tab; questions generated from your own records and questionnaire. | [Careers360](https://competition.careers360.com/articles/how-prepare-for-upsc-ias-interview) |
| SSB PIQ sections: personal details, parents' education and occupation, education with results, NCC, sports, extra-curricular, hobbies, previous attempts, choice of service. Tips: be specific, match certificates, never exaggerate, keep PIQ, self-description and interview consistent, leave nothing blank. | Questionnaire editor (PIQ/DAF) with "fill from profile" and a consistency check against your profile. | [SSBCrackExams — filling the PIQ](https://ssbcrackexams.com/step-by-step-guide-pro-tips-on-how-to-fill-new-online-piq-form-for-ssb-interview/) |
| Typical PIQ-based questions (journey, home town, family, free time, previous attempts …). | Question bank category "From your questionnaire". | [SSBCrackExams — PIQ questions](https://ssbcrackexams.com/sure-shot-questions-asked-from-piq-form-in-ssb-interview/) |
| Senior scientist interviews probe leadership, reproducibility, funding, IP, collaboration, technology transfer and communication. | Research, leadership and project question categories. | [InterviewPrep](https://interviewprep.org/senior-scientist-interview-questions/) |

## Limits of this research

* Character limits for the Naukri headline and summary are recommendations from third-party guides, not
  published Naukri limits; the app labels them "recommended".
* LinkedIn's maximum number of skills could not be confirmed from LinkedIn's own help pages (they were not
  reachable), so the app does not enforce one.
* Indeed's accepted file types and size limit are not stated in its help article; the app recommends PDF or
  DOCX without a size limit.
* Recruitment details in the directory are orientation only. Every entry tells the user to follow the
  actual notification.
