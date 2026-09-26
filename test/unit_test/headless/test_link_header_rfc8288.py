"""Link headers parse with the RFC 8288 Appendix B algorithm.

A ``<`` in an unquoted parameter used to open a phantom target that swallowed
the next link, so ``next_url`` answered with the wrong page.
"""
import pytest

from je_auto_control.utils.link_header import links_by_rel, next_url, parse_link_header


@pytest.mark.parametrize("header, position, title", [
    ("<a>; title=x<y, <b>; rel=next", 0, "x<y"),
    ("<a>; title=x>y, <b>; rel=next", 0, "x>y"),
    ("<a>; rel=prev, <b>; title=a<b<c; rel=next", 1, "a<b<c"),
])
def test_an_angle_bracket_in_an_unquoted_value_stays_in_that_value(header, position, title):
    assert next_url(header) == "b"
    assert parse_link_header(header)[position].params["title"] == title


def test_the_rfc_8288_section_3_5_examples():
    header = ('<http://example.com/TheBook/chapter2>; rel="previous"; title="previous chapter", '
              '</>; rel="http://example.net/foo", '
              '</terms>; rel="copyright"; anchor="#foo", '
              '<http://example.org/>; rel="start http://example.net/relation/other"')
    links = parse_link_header(header)
    assert [link.uri for link in links] == ["http://example.com/TheBook/chapter2", "/", "/terms",
                                             "http://example.org/"]
    assert links[0].params["title"] == "previous chapter"
    assert links[2].params["anchor"] == "#foo"
    assert set(links_by_rel(header)) == {"previous", "http://example.net/foo", "copyright", "start",
                                         "http://example.net/relation/other"}


def test_a_valueless_parameter_is_an_empty_string():
    [link] = parse_link_header("<a>; crossorigin; rel=preload")
    assert link.params == {"crossorigin": "", "rel": "preload"}


def test_relations_split_on_space_and_tab_only():
    assert set(links_by_rel("<a>; rel=\"next\tprefetch\"")) == {"next", "prefetch"}
    assert next_url("<a>; rel=\"a" + chr(0xA0) + "next\"") is None      # NBSP is not RWS


def test_quoted_values_keep_commas_semicolons_and_escapes():
    [link] = parse_link_header('<a>; title="x, \\"y\\"; z"; rel=next')
    assert link.params["title"] == 'x, "y"; z'
    assert link.rel == "next"


def test_empty_elements_are_skipped_and_parsing_stops_at_a_non_link():
    assert [link.uri for link in parse_link_header(" , <a>; rel=next,, <b>")] == ["a", "b"]
    assert [link.uri for link in parse_link_header("<a>, garbage, <b>")] == ["a"]
    assert parse_link_header("<unterminated; rel=next") == []


def test_the_first_occurrence_of_a_parameter_wins():
    assert next_url('<https://a/p2>; rel="next"; rel="prev"') == "https://a/p2"
