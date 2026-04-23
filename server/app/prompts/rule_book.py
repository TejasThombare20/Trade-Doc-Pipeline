"""Rule book extraction prompt."""

from __future__ import annotations

SYSTEM = """You are given a customer's compliance rule book for international
trade documents. Extract a structured list of validation rules.

Each rule targets ONE canonical field:
  consignee_name, hs_code, port_of_loading, port_of_discharge,
  incoterms, description_of_goods, gross_weight, invoice_number

rule_type options and their spec:
  equals   -> { "value": "<exact value>" }
  regex    -> { "pattern": "<python regex>" }
  one_of   -> { "values": ["..", "..", ".."] }
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

Return JSON matching the provided schema exactly."""


USER_PREAMBLE = """Extract the structured rules from this customer rule book."""
