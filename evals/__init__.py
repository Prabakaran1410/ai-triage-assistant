"""Evaluation harness: a labeled message set, run through the real triage
pipeline, scored, and compared with a stored baseline.

Labeling guide (what the expected intent means):
- billing: charges, payments, promo codes, price adjustments, membership fees.
- refund: the customer wants money back, a return-for-refund, or a cancellation
  for money back. Wins over `complaint` when both apply.
- technical_issue: website, app, checkout or tracking-link problems.
- account: login, password, email, 2FA, loyalty points, account status.
- general_question: information about shipping, hours, policies, products.
- complaint: dissatisfaction with service or product, no specific self-service
  answer wanted. These go to a person.
- legal_or_safety: legal threats, chargeback threats, injury or product safety,
  privacy/data-rights requests, fraud and phishing reports. Wins over refund.
- other: sponsorship pitches, spam, unintelligible input.
`intent: null` means the row is adversarial (prompt injection); it is scored on
escalation and forbidden phrases, not on intent.
"""
