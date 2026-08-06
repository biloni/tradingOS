"""Synthetic official investor-relations press-release text, keyed by
ticker — used only by `providers.synthetic_evidence.SyntheticCompanyGuidanceProvider`
and its parser (`_parse_guidance_release()`) to demonstrate real guidance
parsing rather than a canned lookup. Fictional company, fictional
numbers — not a reproduction of any real company's actual release.
"""

SYNTHETIC_GUIDANCE_RELEASES: dict[str, str] = {
    "AMD": (
        "SUNNYVALE, Calif. -- (Synthetic Test Wire) -- Example Semiconductor "
        "Corp today announced financial guidance. For Q3 2026, the Company "
        "expects revenue in the range of $8.0 billion to $8.4 billion, "
        "reflecting continued strength in data center demand."
    ),
}
