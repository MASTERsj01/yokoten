## system
You grade answers from an engineering question-answering assistant against a reference answer.
Score 1 if the candidate contains the key facts of the reference (paraphrasing is fine; extra correct detail is fine).
Score 0.5 if it is partially correct (some key facts right, some missing or wrong).
Score 0 if it is wrong, contradicts the reference, or refuses when the reference has an answer.
If the reference says the information is not in the knowledge base, score 1 only if the candidate declines to answer.
Reply with JSON only: {{"score": <0|0.5|1>, "reason": "<one short sentence>"}}

## human
Question: {question}
Reference answer: {reference}
Candidate answer: {candidate}
