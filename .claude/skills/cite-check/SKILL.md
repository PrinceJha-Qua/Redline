---
name: cite-check
description: Check every case citation in a brief, memo or draft with Redline before it is filed or relied on. Use whenever you write or review US case citations.
---

# Check citations with Redline

1. Call `check_citations` with the full text (the draft you wrote, or the file the user gave you).
2. For each citation, act on the verdict:
   - **FABRICATED**: the citation cannot be right. Do not keep it. Look the case up with
     `search_cases` by name: if it exists, replace the citation with the one returned; if not,
     remove the proposition or tell the user it has no support.
   - **VERIFIED, overruled**: do not cite it as current law. Say what overruled it, or cite the
     overruling case instead.
   - **VERIFIED, caution**: the case rests on an overruled decision (shown in `stands_on`). Check
     that the brief does not use it for that rule.
   - **UNVERIFIABLE**: outside Redline's data (only U.S. Reports to 2014 and F.3d are covered). It is
     not evidence of a fake; tell the user it was not checked.
3. Run `check_citations` again on the revised text, and report the summary line to the user.

Never describe a citation as verified unless Redline returned VERIFIED for it.
