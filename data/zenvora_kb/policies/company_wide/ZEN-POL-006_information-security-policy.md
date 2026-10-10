# Information Security Policy

**Reference No:** ZEN-POL-006 | **Version:** 3 | **Revision:** 1  
**Policy type:** Company-wide  
**Effective Date:** 1 Oct 2025 | **Next Review:** 30 Nov 2026  
**Owning Department:** IT & Information Security  
**Prepared By:** Manoj Thomas (IT & Security Manager (CISO))  
**Reviewed By:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**Approved By:** Arvind Kulkarni (Founder & Chief Executive Officer)  
**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  
**Related policies:** ZEN-POL-004 (Progressive Discipline Policy); ZEN-POL-005 (Acceptable Use and Electronic Communication Policy); ZEN-DPL-ITS-01 (Asset Management and Access Control Policy); ZEN-DPL-DCL-01 (Cloud Operations, On-call and Incident Management Policy); ZEN-DPL-DAI-01 (Data Governance and Responsible AI Policy)

## Policy History

| Revision | Amendment description | Effective date | Reviewed by | Approved by |
|---|---|---|---|---|
| 1 | First security policy | 1 Aug 2018 | IT & Security Manager (CISO) | Founder & CEO |
| 2 | Aligned to ISO 27001 controls | 1 Sep 2024 | IT & Security Manager (CISO) | Founder & CEO |
| 3.0 | ISO 27001:2022 certification baseline | 20 Feb 2025 | IT & Security Manager (CISO) | Founder & CEO |
| 3.1 | Added CERT-In reporting step | 1 Oct 2025 | IT & Security Manager (CISO) | Founder & CEO |

## Table of Contents

| S.# | Topic |
|---|---|
| 1 | Objective |
| 2 | Applies to |
| 3 | Data classification |
| 4 | Accounts and devices |
| 5 | Reporting incidents |
| 6 | Access management |
| 7 | Training |
| 8 | Third parties |
| 9 | Physical security |
| 10 | Non-compliance |
| 11 | Disclaimer |

## 1. Objective

To protect the confidentiality, integrity and availability of Zenvora's and its customers' information, and to meet ISO 27001, SOC 2 and applicable law including India's Digital Personal Data Protection Act, 2023.

## 2. Applies to

All employees, interns, consultants, contractors and partners with access to Zenvora information.

## 3. Data classification

| Class | Examples | Handling |
|---|---|---|
| Public | Website content, published blogs | No restriction. |
| Internal | Policies, org charts, internal wiki | Company people only. |
| Confidential | Product roadmaps, financials, contracts, source code | Need-to-know. Encrypted in transit and at rest. |
| Restricted | Customer conversations, personal data, credentials, keys | Named access only, masked in analytics, never in unapproved tools. |

## 4. Accounts and devices

- Sign in through Okta with multi-factor authentication. Passphrases must have at least 14 characters. Never share accounts.
- Company laptops are encrypted and managed (MDM). USB storage is blocked by default.
- Lock your screen when away. Do not leave Restricted data on screens in public places.

## 5. Reporting incidents

Report any suspected security incident (lost device, phishing click, wrong-recipient email, suspected breach) within 1 hour of discovery to security@zenvora.example or in Slack #incidents.

- The CISO classifies the incident and leads the response with DevOps & Cloud.
- Where legally required, the CISO reports incidents to CERT-In within 6 hours of becoming aware.
- Customers are notified as required by their contracts, normally within 72 hours of confirmation.

## 6. Access management

Access follows least privilege and is reviewed every quarter. Leavers lose access within 4 hours of their last working hour (see ZEN-DPL-ITS-01).

## 7. Training

Every new joiner completes security awareness training within 30 days of joining. Everyone repeats it annually and takes part in quarterly phishing simulations.

## 8. Third parties

Suppliers who handle Confidential or Restricted data need a security review and a signed data processing agreement before access is granted.

## 9. Physical security

Visitors sign in and are escorted. Access cards are personal. Report lost cards the same day.

## 10. Non-compliance

Violations are handled under the Progressive Discipline Policy (ZEN-POL-004). Intentional breaches are not subject to progressive steps.

## 11. Disclaimer

Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements.

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
