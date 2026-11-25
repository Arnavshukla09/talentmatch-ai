#include "education.hpp"
#include "../skills/trie.hpp"
#include <regex>
#include <algorithm>
#include <sstream>
#include <cctype>
#include <cmath>
#include <unordered_set>
#include <numeric>
#include <iterator>

namespace talentmatch {

// ---------------------------------------------------------------------------
// String utilities
// ---------------------------------------------------------------------------
static std::string ed_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

// ---------------------------------------------------------------------------
// EducationFeatureExtractor
// ---------------------------------------------------------------------------

double EducationFeatureExtractor::degree_level(const std::string& deg) {
    std::string l = ed_lower(deg);
    if (l.find("phd") != std::string::npos  || l.find("docto") != std::string::npos) return 1.00;
    if (l.find("master") != std::string::npos || l.find("m.tech") != std::string::npos ||
        l.find("mtech") != std::string::npos  || l.find("mba") != std::string::npos  ||
        l.find("m.s.") != std::string::npos   || l.find("msc") != std::string::npos) return 0.80;
    if (l.find("bachelor") != std::string::npos || l.find("b.tech") != std::string::npos ||
        l.find("btech") != std::string::npos   || l.find("bsc") != std::string::npos  ||
        l.find("b.s.") != std::string::npos    || l.find("b.e.") != std::string::npos ||
        (l.size() >= 2 && l.substr(0,2) == "be")) return 0.60;
    if (l.find("associate") != std::string::npos || l.find("diploma") != std::string::npos) return 0.40;
    if (l.find("high school") != std::string::npos || l.find("secondary") != std::string::npos) return 0.20;
    return 0.0;
}

double EducationFeatureExtractor::field_match(const std::string& field, const std::string& jd_text) {
    if (field.empty()) return 0.0;
    std::string fl = ed_lower(field);
    std::string jl = ed_lower(jd_text);
    // High-value field keywords
    static const std::vector<std::pair<std::string,double>> fields = {
        {"computer science",1.0},{"software engineering",1.0},{"electrical engineering",0.85},
        {"data science",1.0},{"machine learning",1.0},{"mathematics",0.75},{"statistics",0.75},
        {"information technology",0.90},{"computer engineering",0.95},{"physics",0.60},
        {"mechanical engineering",0.50},{"finance",0.70},{"business",0.60},{"accounting",0.65},
        {"biology",0.40},{"chemistry",0.40},{"nursing",0.80},{"medicine",0.80},
        {"law",0.70},{"marketing",0.65},{"psychology",0.40}
    };
    double best = 0.0;
    for (const auto& [kw, score] : fields) {
        if (fl.find(kw) != std::string::npos && jl.find(kw) != std::string::npos) {
            best = std::max(best, score);
        }
        if (fl.find(kw) != std::string::npos) best = std::max(best, score * 0.5);
    }
    return best;
}

double EducationFeatureExtractor::normalize_gpa(const std::string& gpa_str) {
    if (gpa_str.empty()) return 0.0;
    static const std::regex num_re(R"((\d+\.?\d*))");
    std::sregex_iterator it(gpa_str.begin(), gpa_str.end(), num_re);
    std::sregex_iterator end;
    std::vector<double> nums;
    for (; it != end; ++it) nums.push_back(std::stod((*it)[0].str()));
    if (nums.empty()) return 0.0;
    double val = nums[0];
    double scale = (nums.size() >= 2) ? nums[1] : (val <= 4.0 ? 4.0 : 100.0);
    return std::min(1.0, val / scale);
}

bool EducationFeatureExtractor::prestigious_institution(const std::string& inst) {
    std::string l = ed_lower(inst);
    static const std::vector<std::string> top = {
        "iit","iim","mit","stanford","harvard","carnegie mellon","princeton",
        "caltech","columbia","yale","oxford","cambridge","berkeley","chicago",
        "nit","bits","iisc","vit","srm","manipal","anna university"
    };
    for (const auto& t : top)
        if (l.find(t) != std::string::npos) return true;
    return false;
}

bool EducationFeatureExtractor::degree_required(const std::string& jd_text) {
    std::string l = ed_lower(jd_text);
    return l.find("degree required") != std::string::npos ||
           l.find("bachelor") != std::string::npos ||
           l.find("b.s.") != std::string::npos;
}

double EducationFeatureExtractor::recency_score(const std::string& end_date) {
    // Extract year
    static const std::regex yr_re(R"(\b(19|20)(\d{2})\b)");
    std::smatch m;
    int year = 2015;
    if (end_date == "Present" || end_date.empty()) return 1.0;
    if (std::regex_search(end_date, m, yr_re)) year = std::stoi(m[0].str());
    double age = std::max(0.0, 2026.0 - static_cast<double>(year));
    return std::max(0.0, 1.0 - age / 20.0); // 20 years old = score 0
}

void EducationFeatureExtractor::extract(const Resume& resume, const std::string& jd_text,
                                         FeatureVector& fv)
{
    const auto& edu = resume.education;
    if (edu.empty()) {
        for (const auto& n : {"num_degrees","highest_degree_level","degree_field_match",
            "gpa_normalized","has_gpa","is_currently_studying","num_institutions",
            "education_recency_score","prestigious_institution_flag","degree_requirement_met"})
            fv.set(n, 0.0);
        return;
    }

    double max_level = 0.0, max_gpa = 0.0, max_field = 0.0, max_recency = 0.0;
    bool has_gpa = false, is_studying = false, prestige = false;
    std::unordered_set<std::string> institutions;

    for (const auto& e : edu) {
        max_level   = std::max(max_level, degree_level(e.degree));
        max_field   = std::max(max_field, field_match(e.field_of_study, jd_text));
        max_recency = std::max(max_recency, recency_score(e.end_date));
        if (!e.gpa.empty()) {
            double g = normalize_gpa(e.gpa);
            max_gpa = std::max(max_gpa, g);
            has_gpa = true;
        }
        if (e.end_date == "Present" || ed_lower(e.end_date) == "current") is_studying = true;
        if (!e.institution.empty()) {
            institutions.insert(ed_lower(e.institution));
            if (prestigious_institution(e.institution)) prestige = true;
        }
    }

    fv.set("num_degrees",              std::min(1.0, static_cast<double>(edu.size()) / 3.0));
    fv.set("highest_degree_level",     max_level);
    fv.set("degree_field_match",       max_field);
    fv.set("gpa_normalized",           max_gpa);
    fv.set("has_gpa",                  has_gpa ? 1.0 : 0.0);
    fv.set("is_currently_studying",    is_studying ? 1.0 : 0.0);
    fv.set("num_institutions",         std::min(1.0, static_cast<double>(institutions.size()) / 3.0));
    fv.set("education_recency_score",  max_recency);
    fv.set("prestigious_institution_flag", prestige ? 1.0 : 0.0);
    fv.set("degree_requirement_met",   (degree_required(jd_text) && max_level >= 0.6) ? 1.0 :
                                       (!degree_required(jd_text)) ? 0.5 : 0.0);
}

// ---------------------------------------------------------------------------
// ProjectFeatureExtractor
// ---------------------------------------------------------------------------
void ProjectFeatureExtractor::extract(const Resume& resume, const std::string& jd_text,
                                       const std::vector<std::string>& jd_techs,
                                       FeatureVector& fv)
{
    const auto& proj = resume.projects;
    if (proj.empty()) {
        for (const auto& n : {"num_projects","avg_technologies_per_project","project_link_ratio",
            "project_tech_overlap","project_domain_relevance","has_open_source",
            "avg_project_desc_length","project_quantification_score"})
            fv.set(n, 0.0);
        return;
    }

    double tech_total = 0.0;
    int with_links = 0, with_desc = 0;
    bool has_os = false;
    double desc_len_total = 0.0;
    std::unordered_set<std::string> all_techs;

    // Matched JD techs
    std::unordered_set<std::string> jd_tech_set;
    for (const auto& t : jd_techs) jd_tech_set.insert(ed_lower(t));

    int proj_with_quant = 0;
    static const std::regex quant_re(R"(\d+\s*(%|x|×|k|\$|ms|users))");

    for (const auto& p : proj) {
        tech_total += static_cast<double>(p.technologies_used.size());
        if (!p.url.empty()) ++with_links;
        if (!p.description.empty()) {
            ++with_desc;
            desc_len_total += static_cast<double>(p.description.size());
        }
        for (const auto& t : p.technologies_used) all_techs.insert(ed_lower(t));
        if (p.url.find("github") != std::string::npos) has_os = true;
        if (std::regex_search(p.description, quant_re)) ++proj_with_quant;
    }

    double avg_tech = tech_total / static_cast<double>(proj.size());
    double link_ratio = static_cast<double>(with_links) / static_cast<double>(proj.size());
    double avg_desc = (with_desc > 0) ? desc_len_total / static_cast<double>(with_desc) : 0.0;

    // Tech overlap with JD
    int overlap = 0;
    for (const auto& t : all_techs) if (jd_tech_set.count(t)) ++overlap;
    double tech_overlap = jd_tech_set.empty() ? 0.5 :
        std::min(1.0, static_cast<double>(overlap) / static_cast<double>(jd_tech_set.size()));

    // Domain relevance: does project description mention JD keywords?
    std::string jl = ed_lower(jd_text);
    int kw_hits = 0;
    for (const auto& p : proj) {
        std::string dl = ed_lower(p.description) + " " + ed_lower(p.name);
        // Count JD tech terms found in project
        for (const auto& t : jd_tech_set)
            if (dl.find(t) != std::string::npos) ++kw_hits;
    }
    double domain_rel = std::min(1.0, static_cast<double>(kw_hits) / std::max(1.0, static_cast<double>(jd_tech_set.size())));

    fv.set("num_projects",               std::min(1.0, static_cast<double>(proj.size()) / 10.0));
    fv.set("avg_technologies_per_project",std::min(1.0, avg_tech / 8.0));
    fv.set("project_link_ratio",         link_ratio);
    fv.set("project_tech_overlap",       tech_overlap);
    fv.set("project_domain_relevance",   domain_rel);
    fv.set("has_open_source",            has_os ? 1.0 : 0.0);
    fv.set("avg_project_desc_length",    std::min(1.0, avg_desc / 300.0));
    fv.set("project_quantification_score",
           std::min(1.0, static_cast<double>(proj_with_quant) / static_cast<double>(proj.size())));
}

// ---------------------------------------------------------------------------
// CertificationFeatureExtractor
// ---------------------------------------------------------------------------
bool CertificationFeatureExtractor::is_cloud_cert(const std::string& name) {
    std::string l = ed_lower(name);
    return l.find("aws") != std::string::npos || l.find("azure") != std::string::npos ||
           l.find("gcp") != std::string::npos || l.find("google cloud") != std::string::npos ||
           l.find("cloud") != std::string::npos;
}

bool CertificationFeatureExtractor::is_security_cert(const std::string& name) {
    std::string l = ed_lower(name);
    return l.find("security") != std::string::npos || l.find("cissp") != std::string::npos ||
           l.find("ceh") != std::string::npos || l.find("oscp") != std::string::npos;
}

double CertificationFeatureExtractor::recency_score(const std::string& issue_date) {
    if (issue_date.empty()) return 0.5;
    static const std::regex yr_re(R"(\b(20)(\d{2})\b)");
    std::smatch m;
    if (!std::regex_search(issue_date, m, yr_re)) return 0.5;
    double age = std::max(0.0, 2026.0 - std::stod(m[0].str()));
    return std::max(0.0, 1.0 - age / 10.0);
}

bool CertificationFeatureExtractor::jd_mentions_cert(const std::string& cert_name, const std::string& jd_text) {
    std::string l = ed_lower(cert_name);
    std::string jl = ed_lower(jd_text);
    // Check first significant word (>3 chars)
    std::istringstream ss(l);
    std::string word;
    while (ss >> word) {
        if (word.size() > 3 && jl.find(word) != std::string::npos) return true;
    }
    return false;
}

void CertificationFeatureExtractor::extract(const Resume& resume,
                                              const std::string& jd_text,
                                              FeatureVector& fv)
{
    const auto& certs = resume.certifications;
    if (certs.empty()) {
        for (const auto& n : {"num_certifications","num_unique_issuers","has_certifications",
            "jd_cert_match","cert_recency_score","has_cloud_cert","has_security_cert"})
            fv.set(n, 0.0);
        return;
    }

    std::unordered_set<std::string> issuers;
    bool cloud = false, security = false, jd_match = false;
    double max_recency = 0.0;

    for (const auto& c : certs) {
        if (!c.issuing_organization.empty()) issuers.insert(ed_lower(c.issuing_organization));
        if (is_cloud_cert(c.name)) cloud = true;
        if (is_security_cert(c.name)) security = true;
        if (jd_mentions_cert(c.name, jd_text)) jd_match = true;
        max_recency = std::max(max_recency, recency_score(c.issue_date));
    }

    fv.set("num_certifications",  std::min(1.0, static_cast<double>(certs.size()) / 8.0));
    fv.set("num_unique_issuers",  std::min(1.0, static_cast<double>(issuers.size()) / 5.0));
    fv.set("has_certifications",  1.0);
    fv.set("jd_cert_match",       jd_match ? 1.0 : 0.0);
    fv.set("cert_recency_score",  max_recency);
    fv.set("has_cloud_cert",      cloud ? 1.0 : 0.0);
    fv.set("has_security_cert",   security ? 1.0 : 0.0);
}

// ---------------------------------------------------------------------------
// ResumeQualityExtractor
// ---------------------------------------------------------------------------

double ResumeQualityExtractor::section_completeness(const Resume& resume) {
    int present = 0;
    if (!resume.contact.full_name.empty()) ++present;
    if (!resume.contact.email.empty()) ++present;
    if (!resume.summary.empty()) ++present;
    if (!resume.experience.empty()) ++present;
    if (!resume.education.empty()) ++present;
    if (!resume.raw_skills.empty()) ++present;
    if (!resume.projects.empty()) ++present;
    if (!resume.certifications.empty()) ++present;
    return static_cast<double>(present) / 8.0;
}

int ResumeQualityExtractor::count_quantified_global(const Resume& resume) {
    static const std::regex quant_re(R"(\d+\s*(%|x|×|k|\$|million|billion|users|ms|seconds))");
    int count = 0;
    auto scan = [&](const std::string& s) {
        std::sregex_iterator it(s.begin(), s.end(), quant_re);
        std::sregex_iterator end;
        count += static_cast<int>(std::distance(it, end));
    };
    for (const auto& e : resume.experience)
        for (const auto& r : e.responsibilities) scan(r);
    for (const auto& p : resume.projects) scan(p.description);
    return count;
}

double ResumeQualityExtractor::avg_bullet_length(const Resume& resume) {
    double total = 0.0; int count = 0;
    for (const auto& e : resume.experience) {
        for (const auto& r : e.responsibilities) {
            total += static_cast<double>(r.size());
            ++count;
        }
    }
    return (count > 0) ? total / static_cast<double>(count) : 0.0;
}

double ResumeQualityExtractor::formatting_consistency(const Resume& resume) {
    // Heuristic: all experience entries have start/end dates → consistent
    int with_dates = 0;
    for (const auto& e : resume.experience) {
        if (!e.start_date.empty()) ++with_dates;
    }
    int total = static_cast<int>(resume.experience.size());
    return (total > 0) ? static_cast<double>(with_dates) / static_cast<double>(total) : 0.5;
}

void ResumeQualityExtractor::extract(const Resume& resume, FeatureVector& fv,
                                     const std::vector<std::string>& skill_names) {
    // Word count
    std::istringstream ss(resume.raw_text);
    int word_count = static_cast<int>(std::distance(
        std::istream_iterator<std::string>(ss), std::istream_iterator<std::string>()));

    int quant_total = count_quantified_global(resume);
    double bullet_len = avg_bullet_length(resume);

    // Action verb density (global across all bullets)
    static const std::unordered_set<std::string> av{
        "built","developed","designed","implemented","created","led","managed",
        "improved","optimized","reduced","increased","launched","deployed","authored",
        "architected","engineered","refactored","migrated","integrated","automated",
        "delivered","shipped"
    };
    int all_bullets = 0, av_count = 0;
    for (const auto& e : resume.experience) {
        for (const auto& r : e.responsibilities) {
            ++all_bullets;
            std::istringstream ss2(r);
            std::string w; ss2 >> w;
            std::string wl = w;
            for (auto& c : wl) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            if (av.count(wl)) ++av_count;
        }
    }
    double av_density_global = (all_bullets > 0)
        ? static_cast<double>(av_count) / static_cast<double>(all_bullets) : 0.0;

    bool has_links = !resume.contact.linkedin_url.empty() ||
                     !resume.contact.github_url.empty() ||
                     !resume.contact.portfolio_url.empty();

    // Flesch-Kincaid Readability Approximation
    int syllables = 0;
    int sentences = std::max(1, static_cast<int>(resume.experience.size()));
    for (char c : resume.raw_text) {
        c = std::tolower(static_cast<unsigned char>(c));
        if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' || c == 'y') {
            syllables++;
        }
        if (c == '.' || c == '!' || c == '?') sentences++;
    }
    double fk_score = 206.835 - 1.015 * (static_cast<double>(word_count) / sentences) - 84.6 * (static_cast<double>(syllables) / std::max(1, word_count));
    // Normalize FK score (0 to 100 normally, map to 0.0-1.0)
    double readability_score = std::max(0.0, std::min(1.0, fk_score / 100.0));

    // Detect repeated skill mentions, rather than penalizing a diverse skill list.
    // Engine-provided matches also cover resumes without a SKILLS heading.
    AhoCorasickTrie skill_trie;
    std::unordered_set<std::string> unique_skills;
    for (const auto& names : {resume.raw_skills, skill_names}) {
        for (const auto& name : names) {
            const auto normalized = ed_lower(name);
            if (!normalized.empty() && unique_skills.insert(normalized).second)
                skill_trie.add_pattern(normalized, normalized, "");
        }
    }
    skill_trie.build();
    std::unordered_map<std::string, int> mentions;
    for (const auto& match : skill_trie.scan(resume.raw_text)) ++mentions[match.canonical_name];
    int repeated_mentions = 0;
    bool excessive_single_skill = false;
    for (const auto& item : mentions) {
        repeated_mentions += std::max(0, item.second - 3);
        if (item.second >= 10 && static_cast<double>(item.second) / std::max(1, word_count) > 0.10)
            excessive_single_skill = true;
    }
    const bool excessive_repetition = static_cast<double>(repeated_mentions) / std::max(1, word_count) > 0.30;
    double keyword_stuffing_penalty = (word_count >= 30 && (excessive_single_skill || excessive_repetition)) ? 1.0 : 0.0;

    fv.set("section_completeness_score",  section_completeness(resume));
    fv.set("action_verb_density_global",  av_density_global);
    fv.set("quantified_achievements_total", std::min(1.0, static_cast<double>(quant_total) / 20.0));
    fv.set("avg_bullet_length",           std::min(1.0, bullet_len / 150.0));
    fv.set("total_word_count",            std::min(1.0, static_cast<double>(word_count) / 2000.0));
    fv.set("resume_length_score",
           // Penalize very short (<300) or very long (>2500) resumes
           [&]() -> double {
               if (word_count < 100) return 0.2;
               if (word_count < 300) return 0.5;
               if (word_count <= 2000) return 1.0;
               if (word_count <= 2500) return 0.8;
               return 0.6;
           }());
    fv.set("formatting_consistency",      formatting_consistency(resume));
    fv.set("has_summary",                 !resume.summary.empty() ? 1.0 : 0.0);
    fv.set("has_links",                   has_links ? 1.0 : 0.0);
    fv.set("has_contact_info",
           (!resume.contact.email.empty() || !resume.contact.phone.empty()) ? 1.0 : 0.0);
    fv.set("readability_score",           readability_score);
    fv.set("keyword_stuffing_penalty",    keyword_stuffing_penalty);
}

} // namespace talentmatch
