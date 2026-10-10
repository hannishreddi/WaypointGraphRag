# Backend Engineering Standards and Code Review Policy

**Reference No:** ZEN-DPL-BKE-01 | **Version:** 2 | **Revision:** 1  
**Policy type:** Departmental  
**Effective Date:** 6 Jan 2025 | **Next Review:** 1 Dec 2026  
**Owning Department:** Backend Engineering  
**Prepared By:** Karthik Naidu (Director of Engineering, Backend)  
**Reviewed By:** Divya Krishnamurthy (Principal Backend Engineer)  
**Approved By:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  
**Related policies:** ZEN-POL-006 (Information Security Policy); ZEN-DPL-DCL-01 (Cloud Operations, On-call and Incident Management Policy); ZEN-DPL-QAT-01 (Quality Gates and Release Sign-off Policy)

## Policy History

| Revision | Amendment description | Effective date | Reviewed by | Approved by |
|---|---|---|---|---|
| 1 | Engineering standards written | 1 May 2019 | Director of Engineering, Backend | Co-Founder & CTO |
| 2.0 | Rewritten after Project Atlas | 1 Apr 2024 | Principal Backend Engineer | Co-Founder & CTO |
| 2.1 | Dependency patching timelines tightened | 6 Jan 2025 | Principal Backend Engineer | Co-Founder & CTO |

## Table of Contents

| S.# | Topic |
|---|---|
| 1 | Objective |
| 2 | Applies to |
| 3 | Languages and stack |
| 4 | Branching and pull requests |
| 5 | Quality bar |
| 6 | Service-level objectives |
| 7 | Dependencies |
| 8 | Ownership |
| 9 | Disclaimer |

## 1. Objective

To keep backend services reliable, secure and easy to change through consistent engineering practice.

## 2. Applies to

All engineers who change backend code or services.

## 3. Languages and stack

Approved languages are Go and Python (FastAPI). Any other language or datastore needs an Architecture Decision Record (ADR) approved by the Principal Backend Engineer and the Director of Engineering.

## 4. Branching and pull requests

- Trunk-based development with branches that live no longer than 2 days.
- Pull requests should be under 400 changed lines where possible.
- Every change needs CI to pass: build, tests, lint and security scan.
- Review rule: 1 approval for most services. 2 approvals, including one Principal Engineer or Director, for services in the billing, payments and authentication paths.

## 5. Quality bar

- New code must have at least 80 percent unit test coverage.
- Public APIs are versioned. Deprecated public API versions get at least 6 months' notice.
- Database migrations must be backward compatible (expand then contract).
- Secrets live in AWS Secrets Manager, never in code.

## 6. Service-level objectives

Every service defines SLOs. Defaults are 99.9 percent monthly availability and p95 latency under 250 ms. Services must expose metrics, logs and traces.

## 7. Dependencies

Dependency updates are reviewed monthly. Critical vulnerabilities are patched within 7 days and high ones within 14 days.

## 8. Ownership

Each service has a CODEOWNERS entry and a named on-call owner. Service owners join the on-call rota described in ZEN-DPL-DCL-01.

## 9. Disclaimer

Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements.

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
