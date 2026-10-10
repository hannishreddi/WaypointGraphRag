# Quality Gates and Release Sign-off Policy

**Reference No:** ZEN-DPL-QAT-01 | **Version:** 3 | **Revision:** 0  
**Policy type:** Departmental  
**Effective Date:** 1 Apr 2025 | **Next Review:** 1 Dec 2026  
**Owning Department:** Quality Assurance  
**Prepared By:** Deepa Venkatesh (QA Manager)  
**Reviewed By:** Mohan Krishna (Senior QA Automation Engineer)  
**Approved By:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  
**Related policies:** ZEN-DPL-BKE-01 (Backend Engineering Standards and Code Review Policy); ZEN-DPL-FME-01 (Frontend and Mobile Release and Accessibility Policy); ZEN-DPL-DAI-01 (Data Governance and Responsible AI Policy); ZEN-DPL-DCL-01 (Cloud Operations, On-call and Incident Management Policy)

## Policy History

| Revision | Amendment description | Effective date | Reviewed by | Approved by |
|---|---|---|---|---|
| 1 | First release checklist | 1 Feb 2017 | QA Manager | Co-Founder & CTO |
| 2 | Automated gates introduced with Atlas | 1 Jan 2023 | QA Manager | Co-Founder & CTO |
| 3 | Performance and AI evaluation gates added | 1 Apr 2025 | QA Manager | Co-Founder & CTO |

## Table of Contents

| S.# | Topic |
|---|---|
| 1 | Objective |
| 2 | Applies to |
| 3 | Defect severity |
| 4 | Release gate |
| 5 | Sign-off |
| 6 | AI features |
| 7 | Test data |
| 8 | Disclaimer |

## 1. Objective

To make release decisions based on evidence agreed in advance.

## 2. Applies to

All production releases of Zenvora products.

## 3. Defect severity

| Severity | Meaning |
|---|---|
| P0 | Outage, data loss or security hole |
| P1 | Major feature unusable, no workaround |
| P2 | Feature degraded, workaround exists |
| P3 | Minor or cosmetic |

## 4. Release gate

- Zero open P0 or P1 defects.
- No more than 3 open P2 defects, each with a written waiver from the QA Manager.
- Regression suite pass rate of at least 98 percent.
- At least 80 percent unit test coverage on new code.
- Performance test: p95 latency under 300 ms at 2x peak load (k6).
- No critical or high findings in the security scan.

## 5. Sign-off

The QA Manager signs off every production release in Jira. Hotfixes need a smoke test and QA Manager approval within 2 hours.

## 6. AI features

AI releases need the evaluation report from the golden-set harness (ZEN-DPL-DAI-01) attached to the release ticket.

## 7. Test data

Test environments use synthetic or masked data only.

## 8. Disclaimer

Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements.

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
