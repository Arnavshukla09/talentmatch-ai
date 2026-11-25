#include "trie.hpp"
#include <algorithm>
#include <cctype>

namespace talentmatch {

// ---------------------------------------------------------------------------
// Normalize: lowercase, keep alphanumeric + + # .
// ---------------------------------------------------------------------------
std::string AhoCorasickTrie::normalize(const std::string& s) {
    std::string r;
    r.reserve(s.size());
    for (unsigned char c : s) {
        if (std::isalpha(c))  r += static_cast<char>(std::tolower(c));
        else if (std::isdigit(c) || c == '+' || c == '#' || c == '.' || c == '&' || c == '-') r += static_cast<char>(c);
        else r += ' ';
    }
    // Collapse spaces
    std::string out;
    bool last_sp = false;
    for (char c : r) {
        if (c == ' ') { if (!last_sp && !out.empty()) out += ' '; last_sp = true; }
        else { out += c; last_sp = false; }
    }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

int AhoCorasickTrie::new_node() {
    nodes_.emplace_back();
    return static_cast<int>(nodes_.size()) - 1;
}

AhoCorasickTrie::AhoCorasickTrie() {
    new_node(); // root = 0
}

// ---------------------------------------------------------------------------
// add_pattern
// ---------------------------------------------------------------------------
void AhoCorasickTrie::add_pattern(const std::string& pattern,
                                   const std::string& canonical_name,
                                   const std::string& category)
{
    std::string norm = normalize(pattern);
    if (norm.empty()) return;

    int cur = 0;
    for (char c : norm) {
        auto it = nodes_[cur].children.find(c);
        if (it == nodes_[cur].children.end()) {
            int next = new_node();
            nodes_[cur].children[c] = next;
            cur = next;
        } else {
            cur = it->second;
        }
    }
    // Only set if no pattern already registered (prefer canonical over aliases)
    if (nodes_[cur].canonical_name.empty()) {
        nodes_[cur].canonical_name = canonical_name;
        nodes_[cur].category       = category;
        nodes_[cur].pattern_len    = static_cast<int>(norm.size());
    }
}

// ---------------------------------------------------------------------------
// build  — compute failure links via BFS
// ---------------------------------------------------------------------------
void AhoCorasickTrie::build() {
    std::queue<int> q;

    // Root's children: failure → root
    for (auto& [ch, child] : nodes_[0].children) {
        nodes_[child].fail = 0;
        q.push(child);
    }

    while (!q.empty()) {
        int cur = q.front(); q.pop();

        for (auto& [ch, child] : nodes_[cur].children) {
            int fail = nodes_[cur].fail;
            while (fail != 0 && nodes_[fail].children.find(ch) == nodes_[fail].children.end()) {
                fail = nodes_[fail].fail;
            }
            if (nodes_[fail].children.count(ch) && nodes_[fail].children.at(ch) != child) {
                nodes_[child].fail = nodes_[fail].children.at(ch);
            } else {
                nodes_[child].fail = 0;
            }
            // If fail state has an output, propagate it (dictionary link)
            if (!nodes_[nodes_[child].fail].canonical_name.empty() &&
                nodes_[child].canonical_name.empty()) {
                nodes_[child].canonical_name = nodes_[nodes_[child].fail].canonical_name;
                nodes_[child].category       = nodes_[nodes_[child].fail].category;
                nodes_[child].pattern_len    = nodes_[nodes_[child].fail].pattern_len;
            }
            q.push(child);
        }
    }
    built_ = true;
}

// ---------------------------------------------------------------------------
// scan  — find all skill matches in text (word-boundary aware)
// ---------------------------------------------------------------------------
std::vector<TrieMatch> AhoCorasickTrie::scan(const std::string& raw_text) const {
    std::string text = normalize(raw_text);

    std::vector<TrieMatch> raw_matches;
    int cur = 0;

    for (size_t i = 0; i < text.size(); ++i) {
        char c = text[i];

        // Follow failure links until we find a transition or reach root
        while (cur != 0 && nodes_[cur].children.find(c) == nodes_[cur].children.end()) {
            cur = nodes_[cur].fail;
        }
        if (nodes_[cur].children.count(c)) {
            cur = nodes_[cur].children.at(c);
        }

        // Output: collect match at this state
        if (!nodes_[cur].canonical_name.empty()) {
            size_t end = i + 1;
            size_t start = end - static_cast<size_t>(nodes_[cur].pattern_len);

            // Preserve language suffixes, but allow sentence punctuation and
            // compounds such as "Python-based" around ordinary skill names.
            auto is_word_char = [](unsigned char ch) {
                return std::isalnum(ch) || ch == '+' || ch == '#';
            };
            
            bool left_ok  = (start == 0) || !is_word_char(static_cast<unsigned char>(text[start - 1]));
            bool right_ok = (end >= text.size()) || !is_word_char(static_cast<unsigned char>(text[end]));
            if (nodes_[cur].pattern_len == 1) {
                if (start > 0 && (text[start - 1] == '&' || text[start - 1] == '-')) left_ok = false;
                if (end < text.size() && (text[end] == '&' || text[end] == '-')) right_ok = false;
                // A dot within an identifier differs from a sentence-ending dot.
                if (end + 1 < text.size() && text[end] == '.' &&
                    std::isalnum(static_cast<unsigned char>(text[end + 1]))) right_ok = false;
            }

            if (left_ok && right_ok) {
                raw_matches.push_back({
                    start, end,
                    nodes_[cur].canonical_name,
                    nodes_[cur].category,
                    text.substr(start, end - start)
                });
            }
        }
    }

    // Deduplicate: for overlapping matches, prefer longer / earlier canonical
    std::sort(raw_matches.begin(), raw_matches.end(),
        [](const TrieMatch& a, const TrieMatch& b){
            if (a.start != b.start) return a.start < b.start;
            return (a.end - a.start) > (b.end - b.start); // prefer longer
        });

    std::vector<TrieMatch> result;
    size_t last_end = 0;
    for (auto& m : raw_matches) {
        if (m.start >= last_end) {
            result.push_back(m);
            last_end = m.end;
        }
    }

    return result;
}

} // namespace talentmatch
