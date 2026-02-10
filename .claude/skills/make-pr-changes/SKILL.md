---
description: Write high quality, robust unit tests and code fixes for pull request change requests
allowed-tools: Write
---

## Goal
Your goal is to generate a comprehensive set of test cases and code fixes that will fix the issues identified in the latest pull request.

## Step 1
First, carefully analyze the code and the comments. Understand its purpose, inputs, outputs, and any key logic or calculations the code performs. Spend significant time considering all the different scenarios and edge cases that need to be tested.

## Step 2
Next, brainstorm a list of test cases you think will be necessary to fully validate the correctness of the code

## Step 3
For each issue identified, specify the following in a table:
- Objective: The goal of the code fix 
- Tests: what unit tests will cover this issue
- Test Type: The category of the test (e.g. positive test, negative test, edge case, etc.)

It's ok if a single issue has multiple rows if the issue requires multiple tests

## Step 4
After defining all the test cases in tabular format, write out the actual test code for each case. Ensure the test code follows these steps:
1. Arrange: Set up any necessary preconditions and inputs 
2. Act: Execute the code being tested
3. Assert: Verify the actual output matches the expected output

## Step 5

When the code fixes are done and the unit tests pass, submit the changes to the pull request



