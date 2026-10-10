# Data Governance and Responsible AI Policy

**Reference No:** ZEN-DPL-DAI-01 | **Version:** 2 | **Revision:** 0  
**Policy type:** Departmental  
**Effective Date:** 1 Feb 2026 | **Next Review:** 1 Feb 2027  
**Owning Department:** Data & AI  
**Prepared By:** Ananya Bhattacharya (Head of Data & AI)  
**Reviewed By:** Manoj Thomas (IT & Security Manager (CISO))  
**Approved By:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  
**Related policies:** ZEN-POL-005 (Acceptable Use and Electronic Communication Policy); ZEN-POL-006 (Information Security Policy); ZEN-DPL-QAT-01 (Quality Gates and Release Sign-off Policy); ZEN-DPL-DCL-01 (Cloud Operations, On-call and Incident Management Policy)

## Policy History

| Revision | Amendment description | Effective date | Reviewed by | Approved by |
|---|---|---|---|---|
| 1 | Data governance rules from Project Beacon | 26 Aug 2024 | Head of Data & AI | Co-Founder & CTO |
| 2 | Responsible AI section added for Sage | 1 Feb 2026 | Head of Data & AI | Co-Founder & CTO |

## Table of Contents

| S.# | Topic |
|---|---|
| 1 | Objective |
| 2 | Applies to |
| 3 | Data handling |
| 4 | Release gate for AI features |
| 5 | Human in the loop |
| 6 | Models and vendors |
| 7 | Incidents |
| 8 | Disclaimer |

## 1. Objective

To use data lawfully and carefully, and to release AI features only when they are accurate, safe and honest about being AI.

## 2. Applies to

All employees and contractors who work with customer or company data or build AI features.

## 3. Data handling

- Data classes follow the Information Security Policy (ZEN-POL-006).
- Personal data in analytics tables is masked. Access is role-based and reviewed quarterly.
- Customer conversation data is kept for the contract term plus 90 days, then deleted. Raw event logs are kept for 13 months. Aggregated analytics are kept for 5 years.
- Data deletion requests are completed within 30 days.

## 4. Release gate for AI features

Before any customer-facing AI feature ships, it must pass the golden-set evaluation run by QA:

- Accuracy of at least 92 percent.
- Hallucination rate below 2 percent.
- Zero failures on the red-team safety set.

## 5. Human in the loop

AI replies about billing disputes, legal matters, health or safety must be reviewed by a human before being sent. Customers must be told when a reply is AI-assisted.

## 6. Models and vendors

The approved model list is maintained by the Head of Data & AI with the CISO. Customer data is never used to train third-party models. Prompts and responses are logged with personal data masked and kept for 90 days.

## 7. Incidents

Harmful, biased or confidently wrong AI behaviour in production is handled as at least a SEV2 incident under ZEN-DPL-DCL-01.

## 8. Disclaimer

Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements.

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
