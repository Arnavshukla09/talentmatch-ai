#pragma once
#include "../include/features.hpp"
#include "../include/resume.hpp"
#include <string>

namespace talentmatch {

class EducationFeatureExtractor {
public:
    static void extract(const Resume& resume, const std::string& jd_text, FeatureVector& fv);

private:
    static double degree_level(const std::string& degree);
    static double field_match(const std::string& field, const std::string& jd_text);
    static double normalize_gpa(const std::string& gpa_str);
    static bool   prestigious_institution(const std::string& inst);
    static bool   degree_required(const std::string& jd_text);
    static double recency_score(const std::string& end_date);
};

class ProjectFeatureExtractor {
public:
    static void extract(const Resume& resume, const std::string& jd_text,
                        const std::vector<std::string>& jd_techs, FeatureVector& fv);
};

class CertificationFeatureExtractor {
public:
    static void extract(const Resume& resume, const std::string& jd_text, FeatureVector& fv);

private:
    static bool is_cloud_cert(const std::string& name);
    static bool is_security_cert(const std::string& name);
    static double recency_score(const std::string& issue_date);
    static bool jd_mentions_cert(const std::string& cert_name, const std::string& jd_text);
};

class ResumeQualityExtractor {
public:
    static void extract(const Resume& resume, FeatureVector& fv,
                        const std::vector<std::string>& skill_names = {});

private:
    static double section_completeness(const Resume& resume);
    static int    count_quantified_global(const Resume& resume);
    static double avg_bullet_length(const Resume& resume);
    static double formatting_consistency(const Resume& resume);
};

} // namespace talentmatch
