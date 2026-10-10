# Project Atlas

**Project ID:** PJ01 | **Status:** Completed | **Start:** 1 Aug 2022 | **End:** 31 Mar 2024

**Executive sponsor:** Meera Subramanian (Co-Founder & Chief Technology Officer)  
**Project lead:** Karthik Naidu (Director of Engineering, Backend)  
**Departments involved:** Backend Engineering, DevOps & Cloud Infrastructure, Quality Assurance

## Summary

Break the original Django monolith behind Pulse into Go and FastAPI services running on Kubernetes.

## Goals

- Cut deploy time from days to under an hour
- Bring p95 API latency below 250 ms
- Let teams deploy services independently

## Outcomes

- Deploy time fell from about 3 days to 40 minutes
- p95 API latency fell from 840 ms to 210 ms
- Monolith retired on 2024-03-31 after 14 services were extracted

## Technology

Go, Python (FastAPI), Kafka, PostgreSQL, Kubernetes (EKS), Terraform

## Team

| Employee ID | Name | Department | Role on project |
|---|---|---|---|
| ZV-1003 | Karthik Naidu | Backend Engineering | Delivery lead |
| ZV-1004 | Divya Krishnamurthy | Backend Engineering | Chief architect |
| ZV-1013 | Naveen Reddy | Backend Engineering | Billing and metering services |
| ZV-1028 | Sneha Hegde | Backend Engineering | Notification and webhook services |
| ZV-1005 | Prakash Raman | DevOps & Cloud Infrastructure | Platform and migration lead |
| ZV-1026 | Nikhil Joshi | DevOps & Cloud Infrastructure | Observability and cut-over reliability |
| ZV-1018 | Mohan Krishna | Quality Assurance | Contract and regression testing |
| ZV-1007 | Deepa Venkatesh | Quality Assurance | QA lead |

## Milestones

- 1 Aug 2022: Kick-off and service map
- 16 Jan 2023: First three services in production
- 4 Sep 2023: Messaging gateway cut over
- 31 Mar 2024: Monolith decommissioned

*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*
