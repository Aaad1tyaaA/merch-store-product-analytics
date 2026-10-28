# AI log

I built this with an AI assistant. I chose the questions and reviewed results; it wrote most of the code.

These are the places where the first approach would have been wrong, and what changed. Each number comes from the notebooks.

1. **Keying sessions on `ga_session_id` alone.** It is a start time in seconds, so different users collide. Alone it gives 349,545 sessions; with `user_pseudo_id` it gives 360,129. The difference merges 10,584 sessions of different people.

2. **Counting purchase events as orders.** There are 5,692 purchase events but 4,451 orders. 883 events carry `(not set)` as the transaction id, 23 have none, and 335 repeat an id already counted. Summing purchase events would overstate revenue by $54,525 (15.1%).

3. **Treating `traffic_source` as the visit's source.** It is the user's first-touch acquisition source, so every channel result is labelled "first-touch channel". It also varies across one user's events for 39,900 users in this obfuscated sample, so `dim_users` takes the most frequent value instead of an arbitrary one.

4. **Mixing UTC and property dates.** Property dates equal UTC dates in this sample. DuckDB, though, renders timestamps in the machine's time zone, and on an IST machine that moves 993,380 events to a different date. Every connection now sets UTC.

5. **Assuming a strict funnel sequence.** Sessions reach later steps without earlier ones: 1,603 checkouts without an add to cart inside the funnel window. The funnel counts presence of each event, the gaps are logged, and a test asserts no bar grows.

6. **Running the funnel over all 92 days.** The first funnel showed 5,145 checkouts without a cart and a view-to-cart rate of 19.7%. The daily inventory showed `add_to_cart` was not tracked for most of November, and valid transaction ids are missing before 11 November and after 25 January. Funnel metrics now use the 61 days where every step is tracked, where view-to-cart is 27.1%.

7. **Using every user first seen by 1 January for 30-day purchase.** Because order ids disappear after 25 January, users first seen in January would not have a full 30 days of order tracking. The activation cohort is users first seen 26 November to 26 December. It starts on 26 November so that first-session add to cart is tracked.

8. **Joining purchased items to categories on `item_id` or their own `item_category`.** Purchase and checkout events use a different id format and category taxonomy. The first category funnel showed Sale with zero orders and another category converting carts into orders at over 100%. Categories now come from each item name's most frequent `view_item` category.

9. **Ranking funnel steps by drop rate as if it disagreed with dollars.** Under a "+1 point" model, dollars at a step are inversely proportional to its conversion rate, so the two rankings are identical by construction. The analysis says so and shows low, base and high scenarios rather than presenting two rankings as independent evidence.

10. **Assuming the test should be mobile checkout.** Mobile converts payment entrants to orders slightly better than desktop (70.8% vs 68.8%). The test target was chosen from the data instead: the step with the most revenue at stake (product view) and its weakest large segment (new sessions).
