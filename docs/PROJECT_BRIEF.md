# EduPulse — Project Brief

## 1. Vision

EduPulse is an explainable academic analytics and student-support platform that helps educators identify changing academic patterns, understand the evidence behind alerts, and track follow-up interventions.

## 2. Problem Statement

Traditional academic dashboards commonly focus on displaying marks, attendance, and summary statistics. These views may not clearly explain emerging academic difficulties or help educators track whether follow-up support was useful.

EduPulse aims to connect academic trends, transparent alerts, and intervention tracking in one system.

## 3. Target Users

- Teachers and academic mentors
- Department administrators
- Students, through an appropriately restricted view

## 4. Core Features

1. Student and subject record management.
2. Assessment, attendance, and assignment tracking.
3. Academic trend analysis over time.
4. Explainable, rule-based academic risk alerts.
5. A what-if simulator for hypothetical changes to selected inputs.
6. Intervention records and follow-up tracking.
7. Role-specific dashboards with visual analytics and student subject details.

## 5. Differentiating Feature

### Explainable Academic Risk and Intervention Engine

The system will identify configurable patterns, such as declining assessment performance or repeated absences, and explain the evidence behind each alert.

The what-if simulator will show how changing hypothetical inputs affects a rule-based classification. It will not claim that simulated changes guarantee real-world academic improvement.

## 6. Initial Technology Stack

- Python
- Flask
- SQLite for local development and PostgreSQL for a persistent deployment database
- HTML, CSS, and JavaScript
- pytest for automated testing
- Git and GitHub for version control

Deployment tooling is included as a starting point. Machine learning remains out of scope unless a justified use case and responsibly governed data become available.

## 7. Quality Requirements

- Validate inputs and handle errors safely.
- Use automated tests for calculations and business rules.
- Separate application logic from presentation.
- Protect sensitive student information.
- Document setup, architecture, design decisions, and limitations.
- Make the application reproducible and suitable for deployment.

## 8. Evaluation Plan

The project will be evaluated on functional correctness, test coverage, usability, explainability, and reproducibility.

If a predictive model is introduced, it will be evaluated separately using suitable metrics and data that avoid leakage. Performance will be compared with a baseline before any claims are made.

## 9. Current Scope

The application now includes role-based faculty/student portals, course and enrollment management, editable attendance sessions, assessment entry and publishing, student subject pages with dated attendance history, explainable academic indicators, a what-if simulator, visual analytics, and support follow-up tracking.

Local development uses SQLite. A PostgreSQL connection option, production WSGI entry point, container recipe, health check, and production cookie/security settings are prepared for a deployment chosen by the project owner.

## 10. Current Status

The product is a portfolio-stage academic support system. Its rules are transparent indicators for human review, and its demo cohort is synthetic. A migration and backup/restore process, hosting-specific setup, and institution-specific privacy/security review are still required before real student records are used.
