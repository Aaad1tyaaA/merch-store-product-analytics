# Decision memo: where the funnel loses buyers

**To:** Head of Growth, Google Merchandise Store · **Data:** GA4 obfuscated sample, sessions 26 Nov 2020 – 25 Jan 2021

**Recommendation:** validate product-view tracking, then test discovery. Four in five sessions (79.8%) end without viewing a product. One extra point at that step is worth about $6.0k a month (range $3.0k–$7.3k), more than any later step. Product-titled landing pages sometimes lack `view_item`, so I validate tracking before testing a best-seller grid for new visitors: three weeks, 29,259 users per arm, powered to detect a 5% lift.

## What the data shows

| Question | Finding | What it means |
|---|---|---|
| Where are buyers lost? | 248,669 sessions → 50,255 view a product (20.2%) → 13,636 add to cart → 6,936 check out → 3,196 order. Session conversion 1.29%, AOV $69.25 | The biggest leaks are before the cart. Checkout steps keep 51–70% of entrants |
| Which leak is worth most? | +1 point is worth $5,966 per 30 days at product view, $4,443 at add to cart, and $1,732–$2,370 at each checkout step. Product view leads in all three sensitivity cases | Start upstream. A point at product view is a 5% relative gain; at the order step it is 1.4% |
| Who struggles most? | New sessions: 18.5% view a product, against 25.3% of returning sessions. They convert at 0.65% against 3.16%, and make up 74.6% of sessions | Target the test at new visitors |
| Is mobile checkout the problem? | No. Mobile converts 70.8% of payment entrants to orders, desktop 68.8% | Not the first test, despite the usual assumption |
| India vs US? | 9.4% of sessions are Indian. Every user-clustered India-minus-US interval includes zero (session conversion 1.26% vs 1.28%) | No clear difference. The Indian funnel is not leakier in this sample |
| What predicts buying later? | First-session non-buyers who add to cart buy within 30 days at 5.6%, against 0.52% for those who don't. Odds ratio 2.0 after controls. Out-of-time AUC 0.87; the top decile holds 63% of later buyers | Use first-session add to cart as the activation metric. It is predictive, not shown to be causal |
| Do new users come back? | 2.4–6.1% of each weekly cohort return the next week (median 4.0%) | Most revenue must come from the first visit |
| Which channels bring buyers? | Paid Search brings 4.9% of new users but 2.7% of their 56-day revenue. Referral brings 15.1% and 18.5% | Review paid search targeting before scaling it |
| Do promotions work? | Clickers convert at 3.57% against 1.23%. Adjusting for device and new/returning mix widens the gap slightly | Self-selected and observational. Only a holdout shows the true effect |

## Recommendation and test

After validating product-view tracking on the homepage and category pages, I would test a best-seller grid for new visitors on eligible landing pages. Randomise by `user_pseudo_id` at the first visit.

- **Primary metric:** first-session product-view rate (baseline 17.95%).
- **Guardrails:** order rate, AOV, revenue per session, page speed.
- **Ship rule:** p < 0.05 on the primary metric, with no guardrail harmed.
- **Process:** decision rule fixed before launch, SRM checked daily, no peeking.
- **Sample:** order rate alone would need about 24 weeks to detect even a 10% change, so the test cannot prove revenue impact. A later holdout settles that.

Full design: `docs/experiment_design.md`. Landing evidence, clustered intervals and bootstrap methods: `docs/evidence_review.md`. The product-view scenario has a conditional sampling interval of $5,641–$6,295; this is distinct from the business sensitivity range above.

## Indian lens

The same six-event funnel is what Indian D2C and e-commerce teams instrument in GA4, Firebase (the same recommended event names in apps), Mixpanel and CleverTap. The CleverTap equivalents are *Product Viewed*, *Added To Cart* and *Charged*. The session, order and activation definitions here transfer directly, including deduplicating orders by transaction id.

For Indian visitors to this store, three testable hypotheses explain why intent might not become orders:

- prices shown only in USD
- international shipping cost revealed late, at checkout
- no UPI or cash-on-delivery option

In this sample Indian sessions convert like US ones. A local storefront should start by measuring the payment-step drop separately for UPI, card and COD.

## Limits

- **Obfuscation:** Google obfuscates this sample and warns that its internal consistency is limited.
- **Tracking gaps:** `add_to_cart` is missing for most of November, and valid order ids stop after 25 January, so funnel metrics use the 61 days where every step is tracked.
- **Users:** a user is a browser cookie, not a person.
- **Channel:** first-touch, not the source of the current visit.
- **Causality:** every comparison here is observational except the proposed test.
