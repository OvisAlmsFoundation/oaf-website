# OAF Website Plan

## 1. Project Foundation

- Project name: OAF Website
- Repository: `oaf-website`
- Purpose: Public website for Ovis Alms Foundation and GraManna.
- Hosting target: Render.
- Site type: Static website.
- Technology: Plain HTML, CSS, and limited JavaScript.
- Repository structure: Separate from the GraManna application repository.
- Development model: May be developed in parallel with GraManna using a separate VS Code window and separate Codex session.
- Python virtual environment: Not required for the website project at this time.

## 2. Initial Website Scope

The first public website will focus on:

- who Ovis Alms Foundation is;
- the Foundation's charitable mission and purpose;
- what GraManna is;
- the general idea behind the GraManna donation and assistance cycle;
- appropriate public contact and organization information;
- privacy, terms, and other appropriate public policy/disclosure pages.

The initial website will keep GraManna explanations general because the application is still being developed and some details may change.

The website should not imply that unfinished GraManna services or Tremendous production fulfillment are already operational.

## 3. Public Truthfulness Rule

- The website must accurately describe Ovis Alms Foundation and GraManna as they actually exist at the time of publication.
- GraManna may be described as being developed or prepared for launch where appropriate.
- The website must not present unfinished app capabilities, unavailable aid delivery, or unapproved Tremendous production fulfillment as already operational.
- Detailed feature-by-feature development status is not required on the public website.

## 4. Tremendous Readiness Purpose

- A live and fully functioning public website is a current prerequisite for Ovis Alms Foundation to seek Tremendous production-account/API reconsideration.
- Tremendous remains the current intended merchant eGift provider for GraManna.
- The website should be a genuine Foundation and program website, not a temporary placeholder created only for provider approval.
- The website does not need to imply that the GraManna application is finished or ready for immediate public use.
- After the website is live, Ovis Alms Foundation can return to Tremendous for production reconsideration.

## 5. Program-Rule and Content Authority

- The public website is an educational and presentation surface, not the authority that creates GraManna business rules.
- Website explanations should derive from authoritative GraManna Program Rules, cargo decisions, and approved user-facing policy sources wherever practical.
- The website should not create a separate conflicting version of GraManna rules.
- If a program rule is unsettled or likely to change, the website should remain general rather than inventing a detailed public rule.
- AI may assist with writing, organization, design, and review, but must not be required as a runtime authority for eligibility, policy, or program decisions.

## 6. Initial GraManna Content Direction

The first website release should emphasize the established charitable concept and donation cycle rather than detailed application functionality.

Initial GraManna explanations should focus on:

- the charitable purpose of GraManna;
- the relationship between Ovis Alms Foundation and the GraManna program;
- the general donor participation concept;
- the general recipient assistance concept;
- the movement from charitable donation to approved assistance;
- the role of gratitude within the overall GraManna concept;
- responsible-use and program safeguards at an appropriate public level.

Detailed social features, tier mechanics, internal workflows, exact thresholds, technical provider behavior, and other evolving application details are not required for the initial public website.

## 7. Relationship to the GraManna Application

- The public Foundation website and the GraManna application are separate projects.
- The public website will explain Ovis Alms Foundation and GraManna to general visitors.
- The GraManna application will remain the operational environment for authenticated user functions.
- The existing GraManna application home page does not need to be removed simply because the public website exists.
- The app home page may later be simplified or adjusted so that the public website carries more of the general Foundation and program explanation.
- Future links between the public website and GraManna application should be designed deliberately when the application is ready for public access.

## 8. Development and Repository Model

- The OAF Website has its own local project folder and its own Git repository.
- GitHub repository: `oaf-website`.
- The website repository is separate from the GraManna application repository.
- Website work may proceed in parallel with GraManna development using separate VS Code windows and separate Codex sessions.
- Changes to the website repository must not alter or depend on the GraManna application working tree.
- Website planning documentation belongs under the `docs/` folder.
- Additional planning documents should be created only when the project becomes large enough to justify separating them from `WEBSITE_PLAN.md`.

## 9. Current Technical Direction

- Hosting target: Render.
- Deployment type: Render Static Site.
- Initial implementation technology: plain HTML, CSS, and limited JavaScript.
- No Python virtual environment is required for the website at this time.
- No database or application backend is currently required for the initial public website.
- More complex technology should be introduced only if a real website requirement later makes it necessary.

## 10. Planning Before Implementation

Before substantial page coding begins, the project should establish:

- website goals and primary audiences;
- initial site map and navigation;
- page-by-page purpose;
- required public content;
- Foundation identity and organization information;
- GraManna public explanation;
- privacy, terms, and other appropriate policy/disclosure surfaces;
- visual and brand direction;
- accessibility expectations;
- domain and deployment arrangement;
- contact method;
- launch-readiness criteria.

The website should be designed deliberately before Codex is asked to build the full site.

## 11. Global Design System and Responsive Behavior

- The entire website must be responsive and adapt cleanly across desktop, tablet, and mobile widths.
- Responsive behavior applies to all page elements, including navigation, typography, images, section spacing, columns, cards, buttons, forms, and footer content.
- Images must resize and crop gracefully without distortion.
- Text should reflow and scale appropriately as available screen space changes.
- Reusable interface elements must use shared global styles rather than page-specific duplicate styling.
- Components of the same type should behave consistently across the website.
- Examples include buttons, links, headings, cards, navigation elements, form controls, and content sections.
- If a shared component has hover, focus, pressed, disabled, animation, or transition behavior, that behavior should remain consistent wherever that component appears.
- Global design values such as colors, spacing, typography, border radius, shadows, and transition behavior should be centrally defined wherever practical.
- Page-specific exceptions should be introduced only when there is a clear design reason.



## 12. Next is About the Foundation.
For this section, I’d actually keep the layout fairly simple rather than adding another image immediately.
My suggestion:
- keep the white band;
- keep the content in a narrower centered column;
- keep the small green eyebrow text;
- larger “About the Foundation” heading;
- eventually 1–2 short paragraphs underneath;
- no button and no image for now.
That gives the page some breathing room after the visually heavy hero and before the GraManna section.