#!/usr/bin/env python3
"""
product_search_full.py

Full Product Searching phase (Home décor) — single-file.

Capabilities:
- Expand product query via OpenAI (or fallback heuristics)
- Search Amazon.in and Flipkart (top N results)
- Extract price text, detect currency, convert to INR
- Filter results by min/max price in INR
- Save JSON output and pretty-print results

Usage examples:
    # headful (visible browsers) - easier to debug:
    python product_search_full.py --query "wooden wall clock" --min 2000 --max 5000

    # headless:
    python product_search_full.py --query "wooden wall clock" --min 2000 --max 5000 --headless

Prereqs (one-time):
    python -m venv venv
    source venv/bin/activate          # mac/linux
    venv\Scripts\activate             # windows
    pip install playwright beautifulsoup4 lxml requests openai
    python -m playwright install

Make sure to set your OpenAI key (optional but recommended for better queries):
    export OPENAI_API_KEY="sk-..."
    # or on Windows:
    setx OPENAI_API_KEY "sk-..."
"""

import os
import re
import json
import time
import argparse
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# -----------------------
# Config
# -----------------------
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")
MAX_RESULTS_PER_SITE = 6
EXCHANGE_API_BASE = "https://api.exchangerate.host"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")  # change if you prefer another model
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)

# Helpful domain hinting for currency detection
DOMAIN_CURRENCY_HINT = {
    "amazon.in": "INR",
    "www.amazon.in": "INR",
    "amazon.com": "USD",
    "www.amazon.com": "USD",
    "flipkart.com": "INR",
    "www.flipkart.com": "INR",
}

# Currency symbols map
SYMBOL_TO_CURRENCY = {
    "₹": "INR", "Rs": "INR", "INR": "INR",
    "$": "USD", "USD": "USD", "US$": "USD",
    "£": "GBP", "GBP": "GBP",
    "€": "EUR", "EUR": "EUR"
}

# -----------------------
# Query expansion (OpenAI primary, fallback heuristic)
# -----------------------
def expand_queries_openai(item_name: str, max_variants: int = 6):
    """
    Try to expand using OpenAI. If no API key or error, raise Exception -> caller should fallback.
    Returns list[str].
    """
    try:
        # support both new and older openai python clients
        try:
            # new-style client (openai>=1.0)
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            messages = [
                {"role": "system", "content": "You are a product-search assistant for home décor."},
                {"role": "user", "content": f"Expand the item name into {max_variants} concise search queries suitable for Amazon/Flipkart.\nItem: \"{item_name}\""}
            ]
            resp = client.chat.completions.create(model=OPENAI_MODEL, messages=messages, max_tokens=200, temperature=0.7)
            text = resp.choices[0].message.content
        except Exception:
            # fallback to legacy openai package usage
            import openai
            openai.api_key = OPENAI_API_KEY
            messages = [
                {"role": "system", "content": "You are a product-search assistant for home décor."},
                {"role": "user", "content": f"Expand the item name into {max_variants} concise search queries suitable for Amazon/Flipkart.\nItem: \"{item_name}\""}
            ]
            resp = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=messages, max_tokens=200, temperature=0.7)
            text = resp.choices[0].message["content"]

        # Split into lines and clean
        lines = [line.strip(" -•0123456789.") .strip() for line in text.splitlines() if line.strip()]
        # also try splitting by commas if single-line
        if len(lines) == 1:
            parts = [p.strip() for p in re.split(r'[,\n;]', lines[0]) if p.strip()]
            if len(parts) > 1:
                lines = parts
        # dedupe keeping order
        seen = set()
        out = []
        for l in lines:
            if l and l not in seen:
                out.append(l)
                seen.add(l)
            if len(out) >= max_variants:
                break
        return out
    except Exception as e:
        raise

def expand_queries_fallback(item_name: str, max_variants: int = 6):
    """
    Simple heuristic fallback for query expansion (no OpenAI).
    Good enough if OpenAI is not available.
    """
    base = item_name.strip()
    variants = [base]
    # add common home-decor suffixes
    for suf in ["for home decor", "for living room", "decorative", "handmade", "rustic", "vintage", "modern"]:
        variants.append(f"{base} {suf}")
    # small synonym swaps for common words
    synonyms = {
        "sofa": ["couch"],
        "rug": ["carpet"],
        "mirror": ["wall mirror"],
        "lamp": ["table lamp", "floor lamp"],
        "clock": ["wall clock", "decorative clock"]
    }
    for w, syns in synonyms.items():
        if w in base.lower():
            for s in syns:
                variants.append(base.lower().replace(w, s))
    # dedupe, return top N
    seen = set()
    out = []
    for q in variants:
        q2 = " ".join(q.split())
        if q2 not in seen:
            out.append(q2)
            seen.add(q2)
        if len(out) >= max_variants:
            break
    return out

def expand_queries(item_name: str, max_variants: int = 6):
    """
    Try OpenAI expansion if API key available; otherwise fallback to heuristic.
    """
    if OPENAI_API_KEY:
        try:
            return expand_queries_openai(item_name, max_variants=max_variants)
        except Exception as e:
            print(f"[warn] OpenAI expansion failed, falling back: {e}")
            return expand_queries_fallback(item_name, max_variants=max_variants)
    else:
        print("[info] OPENAI_API_KEY not found — using heuristic query expansion")
        return expand_queries_fallback(item_name, max_variants=max_variants)

# -----------------------
# Price extraction / currency detection / conversion
# -----------------------
def extract_price_and_currency(price_str, site_hint_currency=None):
    """
    Return (amount_float_or_None, currency_code_or_None, cleaned_price_str)
    """
    if not price_str:
        return None, None, None
    s = price_str.strip().replace('\xa0', ' ').replace('\u200b', '')
    cur = None
    for sym, code in SYMBOL_TO_CURRENCY.items():
        if sym in s:
            cur = code
            break
    if not cur and site_hint_currency:
        cur = site_hint_currency
    # find numeric token
    m = re.search(r'(\d{1,3}(?:[,\d]{0,3})*(?:\.\d+)?)', s)
    if not m:
        m2 = re.search(r'(\d+(\.\d+)?)', s)
        if not m2:
            return None, cur, s
        num_txt = m2.group(1)
    else:
        num_txt = m.group(1)
    num_txt = num_txt.replace(',', '')
    try:
        amount = float(num_txt)
    except:
        amount = None
    return amount, cur, s

def fetch_rates_for_currencies(currencies):
    """
    currencies: set/list of currency codes e.g. {'USD','EUR'}
    Returns dict currency -> rate_to_INR (float)
    Using exchangerate.host (free).
    """
    rates = {}
    for cur in set(currencies):
        if not cur or cur.upper() == "INR":
            rates[cur] = 1.0
            continue
        try:
            r = requests.get(f"{EXCHANGE_API_BASE}/latest", params={"base": cur, "symbols": "INR", "places": 6}, timeout=8)
            data = r.json()
            rate = data.get("rates", {}).get("INR")
            if rate is None:
                # fallback convert
                r2 = requests.get(f"{EXCHANGE_API_BASE}/convert", params={"from": cur, "to": "INR", "amount": 1}, timeout=8)
                rate = r2.json().get("result")
            if rate is None:
                print(f"[warn] couldn't fetch rate for {cur}")
                rates[cur] = None
            else:
                rates[cur] = float(rate)
        except Exception as e:
            print(f"[warn] exchange API error for {cur}: {e}")
            rates[cur] = None
        time.sleep(0.1)
    return rates

def convert_to_inr(amount, from_currency, rates_cache):
    if amount is None:
        return None
    if not from_currency or from_currency.upper() == "INR":
        return float(amount)
    rate = rates_cache.get(from_currency)
    if rate is None:
        return None
    return round(float(amount) * float(rate), 2)

def format_inr(n):
    if n is None:
        return None
    return "₹{:,.2f}".format(n)

# -----------------------
# Site searchers (Playwright + BeautifulSoup)
# -----------------------
def search_amazon_in(query, max_results=MAX_RESULTS_PER_SITE, headless=True):
    """
    Search Amazon India for 'query' and return list of dicts:
    {platform, title, url, price_text, rating_text, source}
    """
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        url = f"https://www.amazon.in/s?k={quote_plus(query)}"
        page.goto(url, timeout=60000)
        try:
            page.wait_for_selector("div.s-main-slot", timeout=12000)
        except:
            pass
        html = page.content()
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.s-main-slot div[data-component-type='s-search-result']")[:max_results]
        for c in cards:
            title_el = c.select_one("h2 a span")
            link_el = c.select_one("h2 a")
            price_el = c.select_one("span.a-offscreen")
            rating_el = c.select_one("span.a-icon-alt")
            title = title_el.get_text(strip=True) if title_el else None
            href = link_el['href'] if link_el and link_el.has_attr('href') else None
            url_full = f"https://www.amazon.in{href}" if href and href.startswith("/") else href
            price_text = price_el.get_text(strip=True) if price_el else None
            rating_text = rating_el.get_text(strip=True) if rating_el else None
            results.append({
                "platform": "Amazon.in",
                "title": title,
                "url": url_full,
                "price_text": price_text,
                "rating_text": rating_text,
                "source": url
            })
        browser.close()
    return results

def search_flipkart(query, max_results=MAX_RESULTS_PER_SITE, headless=True):
    """
    Search Flipkart for 'query' and return list of dicts.
    Flipkart is dynamic; heuristics try to capture product anchors and price text.
    """
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        url = f"https://www.flipkart.com/search?q={quote_plus(query)}"
        page.goto(url, timeout=60000)
        time.sleep(2)
        html = page.content()
        soup = BeautifulSoup(html, "lxml")

        # Try anchors with title attribute
        anchors = soup.select("a[title]")[:max_results*3]
        seen = set()
        found = 0
        for a in anchors:
            href = a.get("href")
            if not href or href in seen:
                continue
            title = a.get("title") or a.get_text(strip=True)
            if not title:
                continue
            # filter short/irrelevant links
            if href.startswith("/") and len(href) < 30:
                # likely not a product
                continue
            url_full = f"https://www.flipkart.com{href}" if href.startswith("/") else href
            # attempt to find price close to anchor
            parent = a.parent
            price_text = None
            for _ in range(4):
                if not parent:
                    break
                pt = parent.find(lambda tag: tag.name in ["div", "span"] and "₹" in (tag.get_text() or ""))
                if pt:
                    price_text = pt.get_text(strip=True)
                    break
                parent = parent.parent
            results.append({
                "platform": "Flipkart",
                "title": title,
                "url": url_full,
                "price_text": price_text,
                "rating_text": None,
                "source": url
            })
            seen.add(href)
            found += 1
            if found >= max_results:
                break

        # fallback: generic anchors
        if not results:
            for a in soup.select("a")[:max_results*5]:
                href = a.get("href")
                text = a.get_text(strip=True)
                if not href or not text:
                    continue
                if "/p/" in href or "itm" in href:
                    url_full = f"https://www.flipkart.com{href}" if href.startswith("/") else href
                    results.append({
                        "platform": "Flipkart",
                        "title": text[:200],
                        "url": url_full,
                        "price_text": None,
                        "rating_text": None,
                        "source": url
                    })
                if len(results) >= max_results:
                    break

        browser.close()
    return results[:max_results]

# -----------------------
# Orchestration utilities
# -----------------------
def detect_currency_from_domain(url):
    try:
        host = urlparse(url).hostname or ""
        return DOMAIN_CURRENCY_HINT.get(host)
    except:
        return None

def unify_results(results, rates_cache):
    """
    Adds amount, currency, price_inr, price_inr_str for each candidate.
    """
    parsed = []
    for p in results:
        site_hint = detect_currency_from_domain(p.get("url") or p.get("source"))
        amount, currency, raw = extract_price_and_currency(p.get("price_text") or "", site_hint)
        if currency is None and site_hint:
            currency = site_hint
        price_inr = None
        if amount is not None:
            if (not currency) or currency.upper() == "INR":
                price_inr = float(amount)
            else:
                rate = rates_cache.get(currency)
                if rate:
                    price_inr = round(float(amount) * float(rate), 2)
                else:
                    price_inr = None
        p2 = dict(p)
        p2.update({
            "amount": amount,
            "currency": currency,
            "raw_price_text": raw,
            "price_inr": price_inr,
            "price_inr_str": format_inr(price_inr) if price_inr is not None else None
        })
        parsed.append(p2)
    return parsed

def apply_price_filter(parsed_results, min_inr=None, max_inr=None):
    out = []
    for p in parsed_results:
        # skip unknown prices (optional: include them)
        if p.get("price_inr") is None:
            continue
        if min_inr is not None and p["price_inr"] < float(min_inr):
            continue
        if max_inr is not None and p["price_inr"] > float(max_inr):
            continue
        out.append(p)
    return out

# -----------------------
# Main pipeline
# -----------------------
def product_search_pipeline(item_name, min_inr=None, max_inr=None, headless=True):
    print(f"[step] Query expansion for: '{item_name}'")
    queries = expand_queries(item_name, max_variants=6)
    print(f"[info] queries: {queries}")

    all_candidates = []
    queries_to_use = queries[:3]  # limit for speed
    for q in queries_to_use:
        print(f"[step] searching for: {q}")
        try:
            a = search_amazon_in(q, max_results=MAX_RESULTS_PER_SITE, headless=headless)
            print(f"  -> Amazon.in: {len(a)} candidates")
            all_candidates.extend(a)
        except Exception as e:
            print(f"[warn] Amazon error for '{q}': {e}")

        try:
            f = search_flipkart(q, max_results=MAX_RESULTS_PER_SITE, headless=headless)
            print(f"  -> Flipkart: {len(f)} candidates")
            all_candidates.extend(f)
        except Exception as e:
            print(f"[warn] Flipkart error for '{q}': {e}")

    # dedupe by url/title
    uniq = {}
    for cand in all_candidates:
        u = cand.get("url") or cand.get("title") or str(time.time())
        if u not in uniq:
            uniq[u] = cand
    candidates = list(uniq.values())
    print(f"[info] total unique candidates before conversion: {len(candidates)}")

    # determine currencies needed
    currencies = set()
    for c in candidates:
        amt, cur, _ = extract_price_and_currency(c.get("price_text") or "", detect_currency_from_domain(c.get("url") or c.get("source")))
        if cur and cur.upper() != "INR":
            currencies.add(cur)
    print(f"[info] currencies detected needing conversion: {currencies}")

    rates = fetch_rates_for_currencies(currencies) if currencies else {}
    # ensure INR is present
    rates_cache = {k: v for k, v in rates.items() if v is not None}
    rates_cache["INR"] = 1.0

    parsed = unify_results(candidates, rates_cache)
    filtered = apply_price_filter(parsed, min_inr=min_inr, max_inr=max_inr)
    # sort by price_inr ascending
    filtered_sorted = sorted(filtered, key=lambda x: (x.get("price_inr") if x.get("price_inr") is not None else 1e12))

    return {
        "queries_used": queries_to_use,
        "raw_candidates": candidates,
        "rates_cache": rates_cache,
        "results": filtered_sorted
    }

# -----------------------
# CLI
# -----------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", "-q", required=True, help="Item name from object detection")
    parser.add_argument("--min", type=float, default=None, help="Min price in INR")
    parser.add_argument("--max", type=float, default=None, help="Max price in INR")
    parser.add_argument("--headless", action="store_true", help="Run browsers headless (default: visible)")
    parser.add_argument("--out", default="results.json", help="Output JSON file")
    args = parser.parse_args()

    res = product_search_pipeline(args.query, min_inr=args.min, max_inr=args.max, headless=args.headless)
    results = res["results"]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(f"[done] {len(results)} results saved to {args.out}\n")

    for i, r in enumerate(results, start=1):
        print(f"[{i}] {r.get('title')}")
        print(f"    platform : {r.get('platform')}")
        print(f"    price    : {r.get('raw_price_text')}  -> {r.get('price_inr_str')}")
        print(f"    rating   : {r.get('rating_text')}")
        print(f"    url      : {r.get('url')}\n")

    if not results:
        print("[note] No results after filtering. Try widening the price range or removing the filter.")

if __name__ == "__main__":
    main()
