"""The knowledge base the evaluation runs against: a fictional outdoor-gear
retailer, Northwind Outfitters. Nothing here is real company data, and the
numbers the eval reports are numbers about *this sample corpus*, not about any
production system.

Two things are deliberate:
- The corpus has gaps (no product catalog, no student discounts, no stores
  outside Portland), so some labeled questions are *unanswerable* and the
  system should escalate rather than guess.
- `holiday-shipping-2024` is old on purpose (age_days), to exercise the
  stale-source escalation rule.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusChunk:
    source_id: str
    title: str
    content: str
    age_days: int = 30


CORPUS: list[CorpusChunk] = [
    CorpusChunk(
        "shipping-domestic",
        "Domestic shipping",
        "Standard shipping within the US takes 3-5 business days and costs a flat $6.95, "
        "free on orders over $75. Expedited (2 business days) is $14.95. Overnight is "
        "$29.95 for orders placed before 1pm Eastern.",
    ),
    CorpusChunk(
        "shipping-international",
        "International shipping",
        "We ship to Canada, the UK and the EU in 7-14 business days. Customers pay any "
        "duties and taxes at delivery. We cannot ship to PO boxes, and fuel canisters and "
        "bear spray cannot be shipped internationally.",
    ),
    CorpusChunk(
        "order-tracking",
        "Order tracking",
        "A tracking email is sent within 24 hours of your order shipping. You can also look "
        "up any order at northwind.example/track with your order number and email.",
    ),
    CorpusChunk(
        "order-changes",
        "Changing or cancelling an order",
        "Orders can be changed or cancelled within 60 minutes of being placed. After that "
        "the order goes to our warehouse and can no longer be modified; you would need to "
        "return it once it arrives.",
    ),
    CorpusChunk(
        "returns-policy",
        "Returns",
        "You can return unused items with tags attached within 60 days of purchase. Returns "
        "for defective items use a prepaid label; other returns have a $5.95 label fee. "
        "Refunds go back to the original payment method 5-7 business days after we receive "
        "the item.",
    ),
    CorpusChunk(
        "final-sale",
        "Final sale items",
        "Clearance items are final sale and cannot be returned or exchanged. Gift cards are "
        "non-refundable.",
    ),
    CorpusChunk(
        "warranty",
        "Warranty",
        "Northwind-branded packs carry a lifetime warranty against manufacturing defects, "
        "and tents carry a 2-year fabric warranty. Normal wear and misuse are not covered. "
        "Submit a claim through the warranty form with photos of the problem.",
    ),
    CorpusChunk(
        "repairs",
        "Repairs",
        "We repair zippers and seams on Northwind gear. Quotes are free and repairs take "
        "about 3 weeks from the day we receive the item.",
    ),
    CorpusChunk(
        "payment-methods",
        "Payment methods",
        "We accept Visa, Mastercard, American Express, PayPal and Apple Pay. We do not "
        "accept personal checks. Pay-later with Klarna splits a purchase into 4 payments "
        "and is available on orders between $50 and $1,000.",
    ),
    CorpusChunk(
        "payment-issues",
        "Declined cards and duplicate charges",
        "A declined card is usually a bank-side block; try another card or contact your "
        "bank. Two charges for one order are typically a pending authorization hold, which "
        "drops off within 3-5 business days. If both charges settle, contact support.",
    ),
    CorpusChunk(
        "promo-codes",
        "Promo codes",
        "One promo code can be used per order and codes cannot be combined. Codes cannot be "
        "applied after an order has been placed.",
    ),
    CorpusChunk(
        "price-adjustment",
        "Price adjustments",
        "If an item you bought drops in price on our site within 14 days of your purchase, "
        "contact support and we will adjust the price on the same item.",
    ),
    CorpusChunk(
        "price-match",
        "Price matching",
        "Northwind does not price match competitors.",
    ),
    CorpusChunk(
        "trailhead-club",
        "Trailhead Club membership",
        "Trailhead Club costs $39 per year and includes free standard shipping, 10% off "
        "orders and early access to sales. It renews automatically each year and can be "
        "cancelled at any time. Memberships not used can be refunded within 14 days.",
    ),
    CorpusChunk(
        "loyalty-points",
        "Loyalty points",
        "You earn 1 point per $1 spent. 500 points can be redeemed for a $10 reward. Points "
        "expire after 18 months of account inactivity.",
    ),
    CorpusChunk(
        "gift-cards",
        "Gift cards",
        "E-gift cards are emailed within minutes of purchase and never expire. Gift cards "
        "cannot be used to buy other gift cards.",
    ),
    CorpusChunk(
        "store-hours",
        "Store and support hours",
        "The Portland store is open Monday to Saturday 10am-8pm and Sunday 11am-6pm, and "
        "is closed on Thanksgiving and Christmas. Phone support is Monday to Friday "
        "8am-6pm Pacific. Chat is available daily 8am-8pm Pacific. Email is answered within "
        "24 hours.",
    ),
    CorpusChunk(
        "contact-support",
        "Contacting support",
        "Call 1-800-555-0142 or email support@northwind.example. For warranty and repair "
        "questions include your order number.",
    ),
    CorpusChunk(
        "account-password-reset",
        "Resetting your password",
        "Use the Forgot password link on the sign-in page. The reset link expires after 30 "
        "minutes. If the email does not arrive, check your spam folder and confirm you used "
        "the address on your account.",
    ),
    CorpusChunk(
        "account-email-change",
        "Changing your account email",
        "Go to Account > Profile to change the email on your account. You will need to "
        "enter your current password.",
    ),
    CorpusChunk(
        "account-deletion-privacy",
        "Deleting your account and data",
        "To have your account and personal data deleted, submit a request through the "
        "privacy portal. Requests are processed within 30 days. Order history is retained "
        "for 7 years for tax purposes.",
    ),
    CorpusChunk(
        "security-2fa",
        "Account security",
        "Two-factor authentication is available in Account > Security using an "
        "authenticator app. Northwind staff never ask for your password or full card number "
        "by phone or email. Report suspected phishing to security@northwind.example.",
    ),
    CorpusChunk(
        "bulk-orders",
        "Bulk and team orders",
        "Orders of 20 or more units of the same item qualify for team pricing. Email "
        "sales@northwind.example and expect a quote within 5 business days.",
    ),
    CorpusChunk(
        "sizing-help",
        "Sizing help",
        "Size guides are on every product page. Our boots run about a half size small. "
        "Size exchanges are free within 60 days.",
    ),
    CorpusChunk(
        "website-issues",
        "Website and app problems",
        "If the site or checkout errors out, clear your browser cache or try another "
        "browser. The mobile app requires iOS 16 or later, or Android 10 or later.",
    ),
    CorpusChunk(
        "recalls-safety",
        "Product recalls and safety",
        "Product safety recalls are posted at northwind.example/recalls. If you own a "
        "recalled product, stop using it and contact support for a remedy.",
    ),
    CorpusChunk(
        "product-care",
        "Caring for your gear",
        "Wash tents and packs by hand with mild soap and air dry. Do not machine wash "
        "or use bleach. Re-apply waterproofing spray once a season.",
    ),
    CorpusChunk(
        "holiday-shipping-2024",
        "Holiday 2024 shipping deadlines",
        "For Christmas delivery in 2024, order by December 18 for standard shipping and "
        "December 21 for expedited shipping.",
        age_days=420,
    ),
]
