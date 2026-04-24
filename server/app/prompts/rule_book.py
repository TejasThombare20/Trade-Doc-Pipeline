"""Rule book extraction prompt."""

from __future__ import annotations

SYSTEM = """You are given a customer's compliance rule book for international
trade documents. Extract a structured list of validation rules.

Each rule targets ONE canonical field:
  consignee_name, hs_code, port_of_loading, port_of_discharge,
  incoterms, description_of_goods, gross_weight, invoice_number

rule_type options and their spec (spec must always match the shape shown):
  equals   -> { "value": "<exact value>" }
  regex    -> { "pattern": "<python regex>" }
  one_of   -> { "values": ["<option1>", "<option2>", ...] }
               IMPORTANT: "values" key is REQUIRED for one_of. List every allowed
               value explicitly. Never emit one_of with an empty spec.
  required -> { }
  range    -> { "min": <number>, "max": <number> }  # numeric only
  custom   -> { "description": "<free-text constraint>" }

severity:
  critical — wrong value blocks customs clearance or contract compliance
  major    — wrong value causes re-submission but no hard block
  minor    — cosmetic or documentation-only concern

GUIDELINES:
- Extract only explicit requirements. Do not invent rules from vague language.
- If the book says "consignee must be ACME CORP", emit equals with that value.
- If multiple Incoterms are allowed, use one_of.
- If a section is ambiguous but clearly a constraint, use "custom" with the
  description copied (near-verbatim) from the rule book.
- If the book names the customer, return it in customer_name_in_book.

VALUE NORMALIZATION:
The strings you emit inside `equals.value` and `one_of.values` become the
canonical values the document extractor will try to match against. Treat them
with care:
- TRIM leading and trailing whitespace on every emitted value.
- COLLAPSE any run of internal whitespace to a single space.
- PRESERVE punctuation, casing, parentheses, codes, and trailing periods
  EXACTLY as the rule book writes them. These details are part of the
  canonical value — the document extractor will emit them verbatim on semantic
  matches, so stripping them here causes real document values to get wrongly
  flagged as mismatches later.
- DO NOT strip a trailing period, comma, or parenthesized code that the rule
  book uses — they are intentional (e.g. "WAL-MART STORES INC." keeps the
  period; "Mumbai (INBOM)" keeps the parenthesized port code).
- DO NOT invent suffixes, port codes, country names, or abbreviations that
  are not present in the rule book.

Examples:
  - Rule book line: `Consignee must be "WAL-MART STORES INC."`
      → `equals.value = "WAL-MART STORES INC."`   (period kept, trimmed)
  - Rule book line: `Allowed loading ports: Mumbai (INBOM), Nhava Sheva (INNSA)`
      → `one_of.values = ["Mumbai (INBOM)", "Nhava Sheva (INNSA)"]`
        (single space before paren, codes kept as written)
  - Rule book line: `Incoterms: FOB Mumbai or FOB Nhava Sheva`
      → `one_of.values = ["FOB Mumbai", "FOB Nhava Sheva"]`
  - Rule book line: `Port of discharge: Los Angeles, USA (USLAX)`
      → `equals.value = "Los Angeles, USA (USLAX)"`
        (comma, country, and code all preserved verbatim)

Submit the rules by calling the `submit_rule_book` tool."""


USER_PREAMBLE = """Extract the structured rules from this customer rule book."""
