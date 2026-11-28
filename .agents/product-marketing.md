# Product Marketing Context

**Document version:** v2
**Last updated:** 2026-11-26
**Source:** Auto-drafted from `durrat_tarim_django` codebase (verified repository facts only; unverified items tagged `[NEED: ...]`).

## 1. Product Overview
- **Brand:** درة تريم (Durrat Tarim)
- **Domain:** `https://durrattarim.com`
- **One-line description:** متجر إلكتروني ومعرض محلي في تريم، وادي حضرموت للقطع العرائسية والأقمشة الفاخرة والأزياء النسائية الراقية، بأسعار معروضة بالريال السعودي واليمني وطلب مباشر عبر واتساب.
- **Category:** Women's bridal pieces, fabrics, and modest/formal attire (قطع عرائسية، أقمشة، أزياء نسائية راقية).
- **Business model:** Retail storefront (`ClothingStore`) with online catalog browsing, verified-account favorites list, and direct WhatsApp order/consultation flow (no online payment gateway friction).
- **Pricing & currencies:** Prices stored in SAR (`price_sar`) and displayed in both SAR and converted YER (`StoreSettings.sar_to_yer_rate`). Payment accepted in-store, via bank transfer, or approved currency exchange companies (شركات الصرافة المعتمدة).
- **Location & service area:** سوق الفتح، تريم، حضرموت، اليمن (`16.05294, 48.97709`). Delivery across Tarim (تريم), Seiyun (سيئون), Wadi Hadhramout (وادي حضرموت), and shipping to other Yemeni governorates via WhatsApp coordination.
- **Hours:** Saturday–Thursday 09:00–21:30; Friday 16:00–22:00 (`Asia/Riyadh`).
- **Return & exchange policy:** Return within 1 day; exchange within 3 days of receipt in original condition, arranged via WhatsApp.
- **Channels:** WhatsApp (`+967783278181` default in `StoreSettings`), Instagram (`@durttrim`), Snapchat (`durttrim`), TikTok (`@durttrim`).

## 2. Target Audience
- **Primary buyers:** Women and families in Tarim, Seiyun, Wadi Hadhramout, and across Yemen shopping for bridal pieces (قطع عرائسية), occasion fabrics (أقمشة), and modest formal wear.
- **Secondary buyers:** Yemeni diaspora / Gulf-based family members purchasing gifts or bridal pieces in SAR for delivery in Hadhramout and Yemen.
- **Jobs to be done:**
  1. Browse current bridal pieces and fabrics with transparent SAR and YER pricing before visiting or messaging.
  2. Save shortlisted pieces to a favorites list and send a single consolidated WhatsApp inquiry.
  3. Confirm sizing, fabric availability, payment method, and local/governorate delivery directly with staff on WhatsApp.

## 3. Problems & Pain Points
- Online checkout gateways are often unavailable or inconvenient for Yemeni shoppers; customers prefer confirming sizing, color, and delivery directly via WhatsApp.
- Dual-currency fluctuations make SAR-only or opaque pricing hard to evaluate locally; shoppers need clear SAR and approximate YER prices side by side.
- Browsing catalog pieces across scattered social media posts makes comparing items or asking about multiple pieces tedious.

## 4. Differentiation
- Structured, searchable, hierarchically categorized web catalog with permanent product URLs instead of buried social posts.
- Dual-currency display (SAR + live-rate YER) on every product card and detail page.
- One-tap pre-filled WhatsApp inquiry per product, plus multi-item WhatsApp batch inquiry from Favorites.
- Physical showroom presence in Souq Al-Fath, Tarim with published hours and clear 1-day return / 3-day exchange policy.

## 5. Brand Voice & Customer Language
- **Language:** Modern Standard Arabic (feminine direct address: `تصفحي`, `اختاري`, `اطلبي`, `مفضلتكِ`, `تواصلي معنا`), RTL-first.
- **Voice attributes:**
  - **Warm and direct:** speaks to the shopper directly (`يمكنكِ تصفح المنتجات والضغط على زر "استفسار واتساب"`), never stiff corporate prose.
  - **Practical and clear:** explains ordering, dual currencies, delivery coverage, and return windows plainly.
  - **Refined without hype:** uses `قطع عرائسية`, `أقمشة`, `أزياء راقية`, `تصاميم محتشمة` without fabricated superlatives.
- **Core Arabic search terms:** درة تريم، قطع عرائسية تريم، أقمشة حضرموت، أزياء نسائية سيئون، متجر أقمشة وادي حضرموت، فساتين ومستلزمات عرائس اليمن.

## 6. Proof Points & Open Gaps
- **Verified facts in repo:** Physical address (سوق الفتح، تريم), working hours, SAR/YER transparent pricing, 1-day return / 3-day exchange policy, WhatsApp direct concierge, verified social accounts.
- **Missing proof (never fabricate):**
  - `[NEED: Verified customer reviews/testimonials with names or Google Business Profile rating]`
  - `[NEED: Year established / years serving Tarim & Hadhramout]`
  - `[NEED: Specific fabric origins or bridal tailoring/alteration details if offered]`
  - `[NEED: Exact delivery timeframes and fees for Tarim, Seiyun, and other governorates]`

## 7. Goals & AI Query Fan-Out Map
- **Primary conversion action:** WhatsApp product inquiry (`product-whatsapp` / `favorites-whatsapp`) and showroom visits in Tarim.
- **Canonical NAP:** `درة تريم` | `سوق الفتح، تريم، وادي حضرموت، اليمن` | `+967 783278181`
- **SEO & AI visibility goal:** Rank #1 for branded queries (`درة تريم`, `Durrat Tarim`, `درة تريم للأقمشة`) and local commercial queries across Tarim, Seiyun, Wadi Hadhramout, and Yemen; surface accurate store details in Google AI Overviews, ChatGPT, and Perplexity.
- **Query Fan-Out Sub-Queries Covered:**
  1. محلات قطع عرائسية وأقمشة في تريم ووادي حضرموت
  2. أسعار الأقمشة والفساتين العرائسية بالريال السعودي واليمني في حضرموت
  3. موقع وأوقات عمل متجر درة تريم للأقمشة سوق الفتح
  4. طلب أقمشة وقطع عرائسية مع التوصيل إلى سيئون ومحافظات اليمن
  5. طرق الدفع والاستبدال في متجر درة تريم عبر واتساب

## Changelog
- **v2 (2026-11-26):** Standardized canonical NAP across templates/JSON-LD/llms.txt and added local/bridal AI query fan-out map.
- **v1 (2026-11-26):** Initial context auto-drafted from repository models, views, templates, and JSON-LD.
