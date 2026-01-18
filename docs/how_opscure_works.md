# How Opscure Works: From Logs to Git Fixes

This document explains the end-to-end flow of Opscure, specifically focusing on how it connects raw logs to your Git-hosted source code to generate and apply fixes.

## The Workflow at a Glance

1.  **Log Ingestion (Listen)**: Opscure streams logs from your services.
2.  **Correlation (Group)**: It detects anomalies and groups related logs into an **Incident Bundle**.
3.  **Enrichment (Connect to Git)**: It maps the error to your source code.
4.  **Analysis (Think)**: The AI diagnoses the root cause using both logs and code.
5.  **Remediation (Act)**: The AI generates a Git Patch and applies it.

---

## Step-by-Step Breakdown

### 1. Log Ingestion & Pattern Matching
*   **What happens**: Your applications stream logs (via stdout/stderr) to the Opscure Agent.
*   **The Logic**: The agent doesn't just store logs; it reads them in real-time. It uses **Pattern Mining** to recognize repeated errors (blocks like `OutOfMemoryError` or `ConnectionTimeout`).
*   **Outcome**: When error rates spike or critical patterns appear, an **Incident** is declared. A `CorrelationBundle` is created, containing the time window of logs.

### 2. Git Context Enrichment (The "Magic" Link)
*   **The User Setup**: You map your services to Git repositories (e.g., `payment-service` → `github.com/org/payment-service`).
*   **Stack Trace Mapping**: When an error contains a stack trace (e.g., `at com.example.Order.process(Order.java:45)`):
    1.  Opscure parses the filename (`Order.java`) and line number (`45`).
    2.  It authenticates with your Git provider.
    3.  It fetches the **exact code snippet** (e.g., lines 35-55) from your repository's `main` branch.
    4.  It checks the **Git History** to see if a recent commit touched this file (often the cause of new bugs).
*   **Result**: The `CorrelationBundle` is enriched. It now contains not just "Error: NPE", but:
    > "Error NPE at line 45. Here is the code at line 45: `user.getName()` (variable `user` might be null). This line was last modified 2 hours ago by `dev@company.com`."

### 3. AI Analysis (The "Brain")
*   **Input**: The AI receives the enriched bundle.
*   **Reasoning**: Because it sees the **Code**, it doesn't guess.
    *   *Without Git*: "It's a Null Pointer, maybe check the user object."
    *   *With Git*: "The variable `user` is initialized to null on line 40 and accessed on line 45 without a check. The recent commit removed the validation logic."
*   **Output**: The AI produces an **AIRecommendation** containing a **Remediation Plan**.

### 4. Remediation (The Fix)
*   **Proposal**: The AI proposes a `git_workflow` fix.
    *   *Example*: "Apply a patch that wraps line 45 in `if (user != null) { ... }`."
*   **Safety Check**: The Confidence Engine evaluates the fix.
    *   *Safe*: If the confidence is high (>0.95) and the action is low-risk.
    *   *Review*: If it involves complex logic, it asks for Human Approval.
*   **Execution**:
    1.  The Agent clones/checks out your repo.
    2.  It configures Git using the bot credentials (or yours, via `git_config`).
    3.  It applies the patch.
    4.  It runs tests (if configured).
    5.  It commits and pushes the fix (or creates a Pull Request).

---

## Configuration

To make this work, the system primarily needs:

1.  **Git Credentials**: A token/key to read your code and push changes.
2.  **Service Mapping**: A config telling Opscure which Git repo belongs to which service/pod.
3.  **Git Identity**: The `user.name` and `user.email` the bot should use for its commits (configured in the Bundle).
