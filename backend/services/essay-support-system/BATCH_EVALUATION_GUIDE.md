# Batch Answer Evaluation System - Implementation Guide

## Overview

The essay-support-system now includes a comprehensive batch answer evaluation system that automatically assesses student responses and determines next steps based on performance.

**Key Features:**
- ✅ Evaluates multiple answers together in a single request
- ✅ Requires 3+ correct answers to PASS
- ✅ Triggers webhook for additional practice when FAIL
- ✅ Predicts next difficulty level when PASS
- ✅ Generates next set of questions automatically

---

## System Flow

### **Scenario 1: Student PASSES (≥3 answers correct)**

```
Student submits 5 answers
         ↓
   Batch evaluation
         ↓
   Correct count: 4 (≥3) → PASSED ✅
         ↓
   Predict next difficulty level
         ↓
   Generate 3 new questions at predicted level
         ↓
   Return response with next_difficulty & next_questions
```

**Response includes:**
- `status`: "PASSED"
- `correct_answers`: 4
- `total_answers`: 5
- `next_difficulty`: "medium" (or "hard" depending on performance)
- `next_questions`: List of 3 generated questions
- `feedback`: Encouraging message with new difficulty level

---

### **Scenario 2: Student FAILS (<3 answers correct)**

```
Student submits 5 answers
         ↓
   Batch evaluation
         ↓
   Correct count: 2 (<3) → FAILED ❌
         ↓
   Trigger n8n webhook for additional practice
         ↓
   If webhook succeeds: Use n8n questions
   If webhook fails: Use local fallback generation
         ↓
   Return response with additional_questions & retry option
```

**Response includes:**
- `status`: "FAILED"
- `correct_answers`: 2
- `total_answers`: 5
- `additional_questions`: List of practice questions (from n8n or local fallback)
- `retry_available`: true
- `webhook_used`: boolean indicating if n8n was used
- `feedback`: Encouraging message with practice suggestions

---

## API Endpoint

### **POST `/api/answers/batch-submit`**

Submit and evaluate multiple student answers in one request.

#### **Request Body**

```json
{
  "answers": {
    "0": "Student's answer to question 1",
    "1": "Student's answer to question 2",
    "2": "Student's answer to question 3",
    "3": "Student's answer to question 4"
  },
  "questions": [
    "What is normalization in databases?",
    "Explain First Normal Form (1NF)",
    "What is a functional dependency?",
    "How does database design improve with normalization?"
  ],
  "topic": "Database Normalization",  // Optional - auto-detected if omitted
  "difficulty": "medium"               // Optional - uses session difficulty if omitted
}
```

#### **Request Headers**

```
x-session-id: <session-uuid>  // Optional - creates new session if omitted
```

#### **Success Response (PASSED - ≥3 correct)**

```json
{
  "session_id": "uuid-here",
  "status": "PASSED",
  "correct_answers": 4,
  "total_answers": 4,
  "feedback": "Excellent! You got 4 out of 4 answers correct. Moving to HARD level.",
  "next_difficulty": "hard",
  "next_questions": [
    {
      "question": "Explain BCNF vs 3NF with a complex example",
      "difficulty": "hard",
      "topic": "Database Normalization",
      "bloom_level": "Analyze"
    },
    // ... 2 more questions
  ],
  "question_results": [
    {
      "question_number": 1,
      "correct": true,
      "feedback": "Perfect explanation!"
    },
    // ... results for all questions
  ],
  "evaluation_result": { /* detailed evaluation data */ }
}
```

#### **Success Response (FAILED - <3 correct)**

```json
{
  "session_id": "uuid-here",
  "status": "FAILED",
  "correct_answers": 2,
  "total_answers": 4,
  "feedback": "Keep practicing! You got 2 out of 4 correct. Review the feedback below and try again with these practice questions.",
  "additional_questions": [
    "What is Normalization and why is it important in database design?",
    "Explain First Normal Form (1NF) with a practical example",
    "How does Second Normal Form (2NF) eliminate partial dependency?"
  ],
  "retry_available": true,
  "webhook_used": true,  // true if n8n webhook succeeded
  "question_results": [
    {
      "question_number": 1,
      "correct": false,
      "feedback": "You mentioned organizing data but missed the concept of reducing redundancy..."
    },
    // ... results for all questions
  ],
  "evaluation_result": { /* detailed evaluation data */ }
}
```

---

## Session Management

The session automatically tracks:
- `submitted_answers`: Dictionary of all submitted answers
- `submitted_questions`: List of all questions asked
- `batch_evaluations`: History of all batch evaluation results
- `difficulty`: Current difficulty level (updated on PASS)

### **Example: View Session Batch Evaluation History**

```python
# In a session object after multiple batch submissions:
sess["batch_evaluations"] = [
  {
    "topic": "Database Normalization",
    "difficulty": "easy",
    "total_answers": 3,
    "correct_answers": 3,
    "passed": true,
    "evaluation": { /* evaluation details */ }
  },
  {
    "topic": "Process Scheduling",
    "difficulty": "medium",
    "total_answers": 4,
    "correct_answers": 2,
    "passed": false,
    "evaluation": { /* evaluation details */ }
  }
]
```

---

## Integration with n8n Webhook

When a student FAILS, the system triggers an n8n webhook with:

```json
{
  "is_correct": false,
  "question_text": "First question from batch",
  "topic": "Database Normalization",
  "feedback": {
    "weaknesses": "Detailed feedback about what was wrong"
  },
  "recommendation": "Review the topics covered in these questions..."
}
```

**Expected n8n Response:**

The webhook should return one of these formats:

```json
{
  "practice_questions": [
    "Question 1",
    "Question 2",
    "Question 3"
  ]
}
```

OR

```json
{
  "questions": [
    "Question 1",
    "Question 2",
    "Question 3"
  ]
}
```

If the webhook fails or times out, the system automatically falls back to local question generation.

---

## Difficulty Level Prediction

When a student PASSES, the system uses this logic to predict the next difficulty:

| Combined Score | Prediction |
|---|---|
| ≥90% | Jump to "hard" |
| 75-89% | Move up one level (easy→medium, medium→hard) |
| 60-74% | Stay same or move up if at "easy" |
| <60% | Stay same or move down if at "hard" |

**Score Calculation:**
```
combined_score = (practice_answers_percentage + original_score) / 2
```

---

## Error Handling

### **Missing Questions**
- **Status Code:** 400
- **Message:** "No questions provided"

### **Missing Answers**
- **Status Code:** 400
- **Message:** "No answers provided"

### **Failed Evaluation**
- Falls back to keyword-based evaluation
- Returns detailed feedback via cloud question generation
- Webhook timeout handled gracefully with local generation

---

## Logging

The system provides detailed console logging for debugging:

```
🔍 [BATCH EVAL] Starting batch evaluation for 4 answers
📚 [BATCH EVAL] Topic: Database Normalization, Difficulty: medium
✅ [BATCH EVAL] Result: 4/4 correct. PASSED: True
🎉 [BATCH EVAL] Student PASSED - predicting next difficulty
📈 [BATCH EVAL] Predicted next difficulty: hard
```

---

## Usage Example (JavaScript/Frontend)

```javascript
// After student answers all questions and clicks "Submit Batch"
const batchSubmission = {
  answers: {
    0: "Normalization organizes data...",
    1: "1NF eliminates repeating groups...",
    2: "A functional dependency...",
    3: "It improves data integrity..."
  },
  questions: [
    "What is normalization?",
    "Explain 1NF",
    "What is a functional dependency?",
    "Why is normalization important?"
  ],
  topic: "Database Normalization",
  difficulty: "easy"
};

const response = await fetch('/api/answers/batch-submit', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'x-session-id': sessionId
  },
  body: JSON.stringify(batchSubmission)
});

const result = await response.json();

if (result.status === "PASSED") {
  // Show success message and next questions
  console.log(`Great! Moving to ${result.next_difficulty} level`);
  displayNextQuestions(result.next_questions);
} else {
  // Show failed message and practice questions
  console.log("Let's practice more!");
  displayPracticeQuestions(result.additional_questions);
}
```

---

## Technology Stack

- **Framework:** FastAPI
- **Evaluation:** OpenAI GPT-3.5-turbo
- **Async:** Python asyncio
- **Webhooks:** n8n (external workflow automation)
- **Fallback:** Local keyword-based evaluation + question bank

---

## Files Modified

1. [sessions.py](app/api/routes/sessions.py) - Enhanced session structure
2. [answers.py](app/api/routes/answers.py) - Added batch evaluation endpoint

---

## Key Validation Rules

✅ At least **3 correct answers = PASS**  
❌ Fewer than **3 correct answers = FAIL**  
⏪ Failed student gets additional practice questions  
⏭️ Passed student gets next difficulty level questions

---

**Status:** ✅ Complete and ready for testing
