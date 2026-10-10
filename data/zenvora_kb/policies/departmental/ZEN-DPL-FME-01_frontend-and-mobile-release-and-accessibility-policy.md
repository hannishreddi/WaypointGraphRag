# Frontend and Mobile Release and Accessibility Policy

**Reference No:** ZEN-DPL-FME-01 | **Version:** 1 | **Revision:** 3  
**Policy type:** Departmental  
**Effective Date:** 1 Mar 2026 | **Next Review:** 1 Mar 2027  
**Owning Department:** Frontend & Mobile Engineering  
**Prepared By:** Farhan Siddiqui (Frontend & Mobile Lead)  
**Reviewed By:** Keerthi Nair (Senior Mobile Engineer)  
**Approved By:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  
**Related policies:** ZEN-DPL-QAT-01 (Quality Gates and Release Sign-off Policy); ZEN-DPL-PDS-01 (Product Development Lifecycle and Design Review Policy); ZEN-DPL-DCL-01 (Cloud Operations, On-call and Incident Management Policy)

## Policy History

| Revision | Amendment description | Effective date | Reviewed by | Approved by |
|---|---|---|---|---|
| 1.0 | Policy written during Project Lighthouse | 10 Mar 2025 | Frontend & Mobile Lead | Co-Founder & CTO |
| 1.1 | Performance budget added | 1 Sep 2025 | Frontend & Mobile Lead | Co-Founder & CTO |
| 1.2 | Staged rollout thresholds | 1 Dec 2025 | Frontend & Mobile Lead | Co-Founder & CTO |
| 1.3 | Release train dates fixed | 1 Mar 2026 | Frontend & Mobile Lead | Co-Founder & CTO |

## Table of Contents

| S.# | Topic |
|---|---|
| 1 | Objective |
| 2 | Applies to |
| 3 | Release trains |
| 4 | Accessibility |
| 5 | Supported platforms |
| 6 | Performance budget |
| 7 | Feature flags and signing |
| 8 | Disclaimer |

## 1. Objective

To ship web and mobile changes predictably, accessibly and without crashing customers' phones.

## 2. Applies to

All engineers and designers shipping Pulse web and mobile apps.

## 3. Release trains

- Web: release every second Tuesday.
- Mobile: monthly release train on the first Tuesday of each month.
- Mobile rollouts are staged: 5 percent, then 25 percent, then 100 percent, with a 24-hour hold between steps. Halt the rollout if crash-free sessions fall below 99.0 percent.

## 4. Accessibility

All new screens meet WCAG 2.1 level AA. Use Zenith Design System components first. An accessibility audit of the web app runs every quarter. The UX lead signs off design quality before release.

## 5. Supported platforms

Web: the latest two versions of Chrome, Edge, Safari and Firefox. Mobile: Android 9 and above, iOS 15 and above.

## 6. Performance budget

Largest Contentful Paint under 2.5 seconds. Initial JavaScript bundle at most 250 KB gzipped. Crash-free sessions at least 99.5 percent.

## 7. Feature flags and signing

All user-facing changes ship behind feature flags. App signing keys are held by DevOps & Cloud in a secured vault and are never stored on personal laptops.

## 8. Disclaimer

Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements.

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
