-- Correctness check for the product-analytics query.
-- Reference: correlated subqueries, one product at a time (no joins to fan out).
WITH ref AS (
  SELECT p.id,
         (SELECT COUNT(DISTINCT oi.order_id) FROM order_items oi WHERE oi.product_id = p.id) AS total_orders,
         COALESCE((SELECT AVG(r.rating) FROM reviews r WHERE r.product_id = p.id), 0)    AS avg_rating
  FROM products p
),
correct AS (  -- identical to QUERIES.correct in api/server.js, without LIMIT/OFFSET
  SELECT p.id, COALESCE(o.total_orders, 0) AS total_orders, COALESCE(r.avg_rating, 0) AS avg_rating
  FROM products p
  LEFT JOIN (SELECT product_id, COUNT(DISTINCT order_id) AS total_orders FROM order_items GROUP BY product_id) o ON o.product_id = p.id
  LEFT JOIN (SELECT product_id, AVG(rating) AS avg_rating FROM reviews GROUP BY product_id) r ON r.product_id = p.id
),
legacy AS (   -- query from the rejected manuscript
  SELECT p.id, COUNT(oi.id) AS total_orders, COALESCE(AVG(r.rating), 0) AS avg_rating
  FROM products p
  LEFT JOIN order_items oi ON oi.product_id = p.id
  LEFT JOIN reviews r ON r.product_id = p.id
  GROUP BY p.id
)
SELECT 'correct' AS variant,
       COUNT(*) FILTER (WHERE c.total_orders <> f.total_orders)                 AS orders_mismatch,
       COUNT(*) FILTER (WHERE abs(c.avg_rating - f.avg_rating) > 1e-9)          AS rating_mismatch,
       COUNT(*) AS products
FROM correct c JOIN ref f USING (id)
UNION ALL
SELECT 'legacy',
       COUNT(*) FILTER (WHERE l.total_orders <> f.total_orders),
       COUNT(*) FILTER (WHERE abs(l.avg_rating - f.avg_rating) > 1e-9),
       COUNT(*)
FROM legacy l JOIN ref f USING (id);

-- Size of the legacy error: how many order_item rows vs distinct orders, inflation factor.
SELECT round(avg(l.total_orders::numeric / NULLIF(f.total_orders, 0)), 2) AS mean_inflation,
       max(l.total_orders::numeric / NULLIF(f.total_orders, 0))           AS max_inflation
FROM (SELECT p.id, COUNT(oi.id) AS total_orders FROM products p
      LEFT JOIN order_items oi ON oi.product_id = p.id
      LEFT JOIN reviews r ON r.product_id = p.id GROUP BY p.id) l
JOIN (SELECT product_id AS id, COUNT(DISTINCT order_id) AS total_orders FROM order_items GROUP BY product_id) f USING (id);
