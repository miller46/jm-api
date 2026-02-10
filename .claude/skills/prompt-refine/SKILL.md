---
argument-hint: [prompt]
description: Improve a prompt
allowed-tools: Write
---

## Input 
Input: $PROMPT


## Goal

Analyze $PROMPT, a prompt for Claude, and improve it. Enure the requirements are followed. Use judgement and apply the best practices when applicable.


## Requirements

The prompt must be as clear, specific, and concise as possible. Never use unnecessary words. 

Instructions must use precise action verbs. Example: "Summarize." is better than "Think about summarizing"

Confirm the output structure is well specified. Use Pydantic validation for structured output such as JSON or XML. 

Break complex tasks down into sub-tasks. Prompt the sub-tasks separately. 


## Best Practices

Prefer a positive framing that provides instructions rather than constraints

Prefer examples for complex tasks. Simple tasks require 0-3 examples. Complex tasks require 3-5 examples. Highly complex tasks may require 5 or more. 


## Output

Write the prompt to file called prompt.txt