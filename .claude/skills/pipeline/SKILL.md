---
argument-hint: [instructions]
description: Orchestrate code and test gen pipeline
allowed-tools: Write, Read
---

## Input 
Input: $INSTRUCTIONS

### 1) Define Spec From $INSTRUCTIONS
Invoke skill: `spec-qna` with input `$INSTRUCTIONS`.

### 2) Read spec.txt and Refine Prompt

Invoke skill: `prompt-refine` with input file `spec.txt`.

### 3) Read prompt.txt and Generate Tests

Invoke skill: `test-gen` with input file `prompt.txt`.

### 4) Write Code

Invoke skill: `code-gen` and repeat until all unit tests pass

### 5) Submit pull request 

Once code is ready, commit code and submit a pull request 