#include "../cpp_core/skills/trie.hpp"
#include "../cpp_core/features/education.hpp"
#include <cassert>
#include <iostream>

int main() {
    talentmatch::AhoCorasickTrie trie;
    for (const auto& name : {"Python", "R", "C", "C++", "C#", ".NET", "Node.js"})
        trie.add_pattern(name, name, "language");
    trie.build();
    for (const auto& text : {"Python", "Python.", "Python-based", "R.", "C.", "C++", "C#", ".NET", "Node.js."})
        assert(trie.scan(text).size() == 1);
    for (const auto& text : {"R&D", "C-level", "CPython", "C.x", "R-based"})
        assert(trie.scan(text).empty());
    talentmatch::Resume repeated;
    repeated.raw_skills = {"Python"};
    for (int i = 0; i < 100; ++i) repeated.raw_text += "Python ";
    talentmatch::FeatureVector flags;
    talentmatch::ResumeQualityExtractor::extract(repeated, flags);
    assert(flags.get("keyword_stuffing_penalty") == 1.0);
    // Recognized skills supplied by the engine also work without a skills section.
    repeated.raw_skills.clear();
    talentmatch::ResumeQualityExtractor::extract(repeated, flags, {"Python"});
    assert(flags.get("keyword_stuffing_penalty") == 1.0);
    talentmatch::Resume short_list;
    short_list.raw_text = "SKILLS Python, Java, SQL, Docker";
    short_list.raw_skills = {"Python", "Java", "SQL", "Docker"};
    talentmatch::ResumeQualityExtractor::extract(short_list, flags);
    assert(flags.get("keyword_stuffing_penalty") == 0.0);
    std::cout << "Native matcher and keyword repetition regressions passed\n";
}
