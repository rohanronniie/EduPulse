
# EduPulse — Student Performance & Academic Analytics System

EduPulse is a web-based academic analytics application designed to organize student academic records and generate transparent, explainable indicators that can help identify where additional academic support may be useful.

The system combines attendance, assessment performance trends, and assignment completion into understandable findings. It also includes a What-If Intervention Simulator to explore hypothetical changes to academic inputs without modifying saved records.

## Key Features

### Student and Course Management
- Register and view student records.
- Create and manage courses.
- Enroll students in courses.
- Prevent duplicate student codes, course codes, and student-course enrollments.

### Academic Record Management
- Record attendance percentages.
- Store assessment scores and track performance trends.
- Record completed and total assignments.
- Associate academic records with student-course enrollments.

### Explainable Academic Analytics
- Evaluate attendance against a configurable threshold.
- Identify assessment score declines.
- Evaluate assignment completion rates.
- Generate findings with reasons and supporting evidence.
- Suggest possible academic support interventions based on the findings.

### What-If Intervention Simulator
- Compare saved academic inputs with a hypothetical scenario.
- Review how changed inputs affect the rule-based findings.
- Keep the saved academic record unchanged during scenario comparison.

### Dashboard
- Display live counts of registered students, courses, enrollments, and academic records.
- Provide navigation to the application's main workflows.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, Flask |
| Database access | SQLAlchemy |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript |
| Testing | pytest |
| Version control | Git and GitHub |

## Application Architecture

The application uses a modular Flask structure.

- `src/__init__.py` — application factory, configuration, blueprint registration, and dashboard.
- `src/database.py` — database engine, session factory, and database initialization.
- `src/models.py` — student, course, and enrollment models.
- `src/academic_models.py` — academic record model.
- `src/academic_engine.py` — rule-based academic evaluation, report generation, intervention recommendations, and scenario comparison.
- `src/student_routes.py` — student management routes.
- `src/course_routes.py` — course management routes.
- `src/enrollment_routes.py` — enrollment management routes.
- `src/academic_routes.py` — academic record, report, and What-If routes.
- `src/templates/` — Jinja templates for the web interface.
- `src/static/` — static assets, including stylesheets.
- `tests/` — automated tests.

## Getting Started

### Prerequisites

- Python 3.14 or a compatible Python version supported by the pinned dependencies.
- Git.

### 1. Clone the repository

```bash
git clone https://github.com/rohanronniie/EduPulse.git
cd EduPulse
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks environment activation, you can use the environment's Python executable directly.

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Run the application

```powershell
python run.py
```

Open the application at:

http://127.0.0.1:5000

The application initializes its SQLite database when configured to do so.

### 5. Run the tests

Stop the development server if it is running, then execute:

```powershell
python -m pytest -q
```

## Typical Workflow

1. Register a student.
2. Create a course.
3. Enroll the student in the course.
4. Create an academic record with attendance, assessment scores, and assignment counts.
5. Open the generated academic report to review findings and supporting evidence.
6. Use the What-If Simulator to compare a hypothetical scenario with the saved data.

## How the Evaluation Works

EduPulse currently uses transparent, rule-based evaluation rather than a trained machine-learning prediction model.

The evaluation considers:
- Attendance percentage.
- Changes between assessment scores.
- Assignment completion rate.

Findings include explanations and evidence so users can understand why an indicator was raised. Intervention suggestions are intended to support review and discussion, not to replace professional judgment.

Thresholds are configurable within the evaluation logic and should be treated as demonstration settings unless validated for a specific educational context.

## Testing

The project includes automated tests for academic evaluation, input validation, database behavior, application routes, and integration workflows.

**Latest recorded test result:** 53 tests passed.

Run the test suite locally to verify the current checkout.

## Limitations and Responsible Use

- The current evaluation is rule-based; it does not establish that a student will fail or predict an individual's future academic outcome.
- Thresholds are not presented as scientifically validated measures of student success.
- Intervention suggestions are informational and should be reviewed by appropriate academic staff.
- The application is a portfolio project and has not been established as production-ready.
- Before deployment with real student information, additional security, access control, privacy, data-retention, backup, and operational safeguards are needed.
- Use synthetic or appropriately authorized data for demonstrations.

## Future Improvements

- Add authentication and role-based access control.
- Improve dashboard insights and academic trend visualizations.
- Add data export and reporting capabilities.
- Evaluate the rule-based approach against appropriately governed, representative data.
- Consider machine learning only if there is a justified use case, suitable data, and a responsible evaluation process.
- Deploy with production-appropriate configuration, monitoring, and security controls.

## Author

**Rohan S**

GitHub: [rohanronniie](https://github.com/rohanronniie)
