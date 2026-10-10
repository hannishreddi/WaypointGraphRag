# Cloud Operations, On-call and Incident Management Policy

**Reference No:** ZEN-DPL-DCL-01 | **Version:** 3 | **Revision:** 1  
**Policy type:** Departmental  
**Effective Date:** 19 Dec 2025 | **Next Review:** 1 Dec 2026  
**Owning Department:** DevOps & Cloud Infrastructure  
**Prepared By:** Prakash Raman (DevOps & Cloud Lead)  
**Reviewed By:** Nikhil Joshi (Site Reliability Engineer)  
**Approved By:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  
**Related policies:** ZEN-POL-006 (Information Security Policy); ZEN-DPL-BKE-01 (Backend Engineering Standards and Code Review Policy); ZEN-DPL-ITS-01 (Asset Management and Access Control Policy)

## Policy History

| Revision | Amendment description | Effective date | Reviewed by | Approved by |
|---|---|---|---|---|
| 1 | First on-call rota | 1 Jan 2018 | DevOps & Cloud Lead | Co-Founder & CTO |
| 2 | Severity model and post-mortems | 1 May 2022 | DevOps & Cloud Lead | Co-Founder & CTO |
| 3.0 | Rewritten after Atlas | 1 Apr 2024 | DevOps & Cloud Lead | Co-Founder & CTO |
| 3.1 | Cost tagging made mandatory (Ember) | 19 Dec 2025 | DevOps & Cloud Lead | Co-Founder & CTO |

## Table of Contents

| S.# | Topic |
|---|---|
| 1 | Objective |
| 2 | Applies to |
| 3 | Severity and response |
| 4 | Incident process |
| 5 | On-call |
| 6 | Changes |
| 7 | Backup and recovery |
| 8 | Infrastructure rules |
| 9 | Disclaimer |

## 1. Objective

To keep production available and recoverable, and to learn from every incident.

## 2. Applies to

All engineers who deploy to or operate production, and incident participants.

## 3. Severity and response

| Severity | Meaning | Acknowledge within | Updates |
|---|---|---|---|
| SEV1 | Full customer-facing outage, data loss or security breach | 15 minutes | Every 30 minutes |
| SEV2 | Major feature degraded | 30 minutes | Every hour |
| SEV3 | Minor degradation | 4 hours | Daily |
| SEV4 | Cosmetic or low impact | Next business day | As needed |

## 4. Incident process

The primary on-call engineer acts as incident commander for SEV1 and SEV2 and opens a channel in Slack #incidents. A blameless post-mortem is published within 5 business days for SEV1 and SEV2.

## 5. On-call

- Weekly rota with a primary and a secondary engineer. Handover is on Monday at 10:00 IST.
- On-call allowance: INR 3,000 per week for primary and INR 1,500 for secondary.
- An engineer paged for more than 1 hour between 22:00 and 06:00 gets a compensatory day off.

## 6. Changes

Standard changes are pre-approved. Normal changes are reviewed in the change review on Tuesdays and Thursdays. Emergency changes need the incident commander's approval. There is a change freeze from 20 December to 2 January.

## 7. Backup and recovery

Tier-1 services have an RPO of 15 minutes and an RTO of 4 hours. Disaster-recovery drills run twice a year, in May and November.

## 8. Infrastructure rules

- All infrastructure is defined in Terraform. Console changes are not allowed except in emergencies.
- Production access uses Okta and just-in-time elevation for 4 hours.
- Every cloud resource must carry cost allocation tags for team and product.

## 9. Disclaimer

Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements.

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
