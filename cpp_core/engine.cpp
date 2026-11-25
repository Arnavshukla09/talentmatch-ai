/**
 * engine.cpp  —  TalentMatch Core: top-level C-linkage entry point
 *
 * This file is compiled into the shared library (libtalentmatch.so / .dll).
 * Python calls engine_score(json_str) via ctypes and receives a JSON response.
 *
 * Pipeline (all in C++, no LLM, no network):
 *   1. Parse request JSON (nlohmann/json)
 *   2. Build SkillTaxonomy from bundled + optional file-based data
 *   3. Parse resume text → Resume struct (ResumeParser)
 *   4. Extract skills from resume + JD (SkillEngine + Aho-Corasick)
 *   5. Perform skill gap analysis
 *   6. Extract all ~85 features (5 feature extractors + retrieval)
 *   7. Run XGBoostRanker (or linear fallback)
 *   8. Compute category scores
 *   9. Generate explanations (ExplanationEngine)
 *  10. Serialize result to JSON and return
 */

#include "include/engine.h"
#include "include/resume.hpp"
#include "include/features.hpp"
#include "include/taxonomy.hpp"
#include "parser/resume_parser.hpp"
#include "skills/skill_engine.hpp"
#include "features/experience.hpp"
#include "features/education.hpp"
#include "features/skills_features.hpp"
#include "retrieval/bm25.hpp"
#include "ranking/xgboost_ranker.hpp"
#include "explainability/explanation_engine.hpp"
#include <nlohmann/json.hpp>

#include <string>
#include <memory>
#include <stdexcept>
#include <fstream>
#include <cstring>
#include <mutex>

using json = nlohmann::json;
using namespace talentmatch;

// ============================================================================
// Engine version
// ============================================================================
static const char* ENGINE_VERSION = "2.0.0";

// ============================================================================
// Bundled default taxonomy (from Python's skill_taxonomy.json data)
// Loaded once at first call. A file-based taxonomy overrides this if found.
// ============================================================================
static const char* DEFAULT_TAXONOMY_JSON = R"({
  "version": "2.0.0-bundled",
  "categories": [
    "Cloud & DevOps", "Core CS Concepts", "Data Engineering",
    "Databases", "Finance & Accounting", "Healthcare",
    "Human Resources", "LLM & RAG", "Legal",
    "MLOps", "Machine Learning & AI", "Programming Languages",
    "Sales & Marketing", "Tools & Platforms", "Web Development"
  ],
  "skills": [
    {"canonical_name":"Python","category":"Programming Languages","aliases":["python3","py"]},
    {"canonical_name":"C","category":"Programming Languages","aliases":[]},
    {"canonical_name":"C++","category":"Programming Languages","aliases":["cpp","c plus plus","cplusplus"]},
    {"canonical_name":"Java","category":"Programming Languages","aliases":[]},
    {"canonical_name":"Go","category":"Programming Languages","aliases":["golang"]},
    {"canonical_name":"Rust","category":"Programming Languages","aliases":[]},
    {"canonical_name":"R","category":"Programming Languages","aliases":[]},
    {"canonical_name":"Scala","category":"Programming Languages","aliases":[]},
    {"canonical_name":"JavaScript","category":"Programming Languages","aliases":["js","javascript es6","ecmascript"]},
    {"canonical_name":"TypeScript","category":"Programming Languages","aliases":["ts"]},
    {"canonical_name":"HTML","category":"Web Development","aliases":["html5"]},
    {"canonical_name":"CSS","category":"Web Development","aliases":["css3"]},
    {"canonical_name":"React","category":"Web Development","aliases":["react.js","reactjs","react js"]},
    {"canonical_name":"Node.js","category":"Web Development","aliases":["node js","nodejs","node"]},
    {"canonical_name":"Express.js","category":"Web Development","aliases":["express","expressjs"]},
    {"canonical_name":"Django","category":"Web Development","aliases":[]},
    {"canonical_name":"Flask","category":"Web Development","aliases":[]},
    {"canonical_name":"FastAPI","category":"Web Development","aliases":[]},
    {"canonical_name":"PyTorch","category":"Machine Learning & AI","aliases":["torch"]},
    {"canonical_name":"TensorFlow","category":"Machine Learning & AI","aliases":["tf"]},
    {"canonical_name":"Keras","category":"Machine Learning & AI","aliases":[]},
    {"canonical_name":"Scikit-learn","category":"Machine Learning & AI","aliases":["sklearn","scikit learn"]},
    {"canonical_name":"OpenCV","category":"Machine Learning & AI","aliases":["cv2"]},
    {"canonical_name":"NumPy","category":"Machine Learning & AI","aliases":["numpy"]},
    {"canonical_name":"Pandas","category":"Machine Learning & AI","aliases":["pandas"]},
    {"canonical_name":"CNN","category":"Machine Learning & AI","aliases":["convolutional neural network","convolutional neural networks"]},
    {"canonical_name":"LSTM","category":"Machine Learning & AI","aliases":["long short term memory"]},
    {"canonical_name":"YOLO","category":"Machine Learning & AI","aliases":["yolov8","yolov5","yolov11"]},
    {"canonical_name":"Computer Vision","category":"Machine Learning & AI","aliases":[]},
    {"canonical_name":"Reinforcement Learning","category":"Machine Learning & AI","aliases":["rl"]},
    {"canonical_name":"LightGBM","category":"Machine Learning & AI","aliases":["light gbm","lgbm","lightgbm"]},
    {"canonical_name":"XGBoost","category":"Machine Learning & AI","aliases":["xgb"]},
    {"canonical_name":"LangChain","category":"LLM & RAG","aliases":[]},
    {"canonical_name":"FAISS","category":"LLM & RAG","aliases":[]},
    {"canonical_name":"Prompt Engineering","category":"LLM & RAG","aliases":[]},
    {"canonical_name":"Retrieval Augmented Generation","category":"LLM & RAG","aliases":["rag","retrieval-augmented generation"]},
    {"canonical_name":"Google Gemini","category":"LLM & RAG","aliases":["gemini api","gemini"]},
    {"canonical_name":"OpenAI API","category":"LLM & RAG","aliases":["openai","chatgpt api"]},
    {"canonical_name":"Docker","category":"Cloud & DevOps","aliases":[]},
    {"canonical_name":"Kubernetes","category":"Cloud & DevOps","aliases":["k8s"]},
    {"canonical_name":"AWS","category":"Cloud & DevOps","aliases":["amazon web services","amazon aws"]},
    {"canonical_name":"GCP","category":"Cloud & DevOps","aliases":["google cloud platform","google cloud"]},
    {"canonical_name":"Azure","category":"Cloud & DevOps","aliases":["microsoft azure","azure cloud"]},
    {"canonical_name":"Terraform","category":"Cloud & DevOps","aliases":[]},
    {"canonical_name":"GitHub Actions","category":"Cloud & DevOps","aliases":["gh actions","github actions ci"]},
    {"canonical_name":"CI/CD","category":"Cloud & DevOps","aliases":["ci cd","cicd","continuous integration","continuous deployment"]},
    {"canonical_name":"MLflow","category":"MLOps","aliases":[]},
    {"canonical_name":"DVC","category":"MLOps","aliases":["data version control"]},
    {"canonical_name":"Airflow","category":"MLOps","aliases":["apache airflow"]},
    {"canonical_name":"SQL","category":"Databases","aliases":[]},
    {"canonical_name":"MySQL","category":"Databases","aliases":[]},
    {"canonical_name":"PostgreSQL","category":"Databases","aliases":["postgres","postgresql db"]},
    {"canonical_name":"MongoDB","category":"Databases","aliases":["mongo"]},
    {"canonical_name":"Redis","category":"Databases","aliases":[]},
    {"canonical_name":"Snowflake","category":"Databases","aliases":[]},
    {"canonical_name":"Kafka","category":"Data Engineering","aliases":["apache kafka"]},
    {"canonical_name":"Spark","category":"Data Engineering","aliases":["apache spark","pyspark"]},
    {"canonical_name":"Hadoop","category":"Data Engineering","aliases":["apache hadoop"]},
    {"canonical_name":"Git","category":"Tools & Platforms","aliases":["github","gitlab"]},
    {"canonical_name":"Jupyter Notebook","category":"Tools & Platforms","aliases":["jupyter","ipython notebook"]},
    {"canonical_name":"Tableau","category":"Tools & Platforms","aliases":[]},
    {"canonical_name":"Power BI","category":"Tools & Platforms","aliases":["powerbi","power bi desktop"]},
    {"canonical_name":"Excel","category":"Tools & Platforms","aliases":["advanced excel","microsoft excel","ms excel"]},
    {"canonical_name":"Streamlit","category":"Tools & Platforms","aliases":[]},
    {"canonical_name":"Gradio","category":"Tools & Platforms","aliases":[]},
    {"canonical_name":"Data Structures and Algorithms","category":"Core CS Concepts","aliases":["dsa","data structures","algorithms"]},
    {"canonical_name":"System Design","category":"Core CS Concepts","aliases":["system design fundamentals","distributed systems design"]},
    {"canonical_name":"Statistics","category":"Core CS Concepts","aliases":["statistical testing","statistical analysis"]},
    {"canonical_name":"Patient Care","category":"Healthcare","aliases":[]},
    {"canonical_name":"Clinical Documentation","category":"Healthcare","aliases":[]},
    {"canonical_name":"HIPAA Compliance","category":"Healthcare","aliases":["hipaa"]},
    {"canonical_name":"Electronic Health Records","category":"Healthcare","aliases":["ehr","ehr systems"]},
    {"canonical_name":"Financial Modeling","category":"Finance & Accounting","aliases":[]},
    {"canonical_name":"GAAP","category":"Finance & Accounting","aliases":[]},
    {"canonical_name":"Bookkeeping","category":"Finance & Accounting","aliases":[]},
    {"canonical_name":"Tax Preparation","category":"Finance & Accounting","aliases":[]},
    {"canonical_name":"QuickBooks","category":"Finance & Accounting","aliases":[]},
    {"canonical_name":"SEO","category":"Sales & Marketing","aliases":["search engine optimization"]},
    {"canonical_name":"Content Marketing","category":"Sales & Marketing","aliases":[]},
    {"canonical_name":"CRM","category":"Sales & Marketing","aliases":["salesforce crm","salesforce","customer relationship management"]},
    {"canonical_name":"Google Analytics","category":"Sales & Marketing","aliases":[]},
    {"canonical_name":"Copywriting","category":"Sales & Marketing","aliases":[]},
    {"canonical_name":"Contract Drafting","category":"Legal","aliases":[]},
    {"canonical_name":"Legal Research","category":"Legal","aliases":[]},
    {"canonical_name":"Litigation","category":"Legal","aliases":[]},
    {"canonical_name":"Compliance","category":"Legal","aliases":["regulatory compliance"]},
    {"canonical_name":"Recruiting","category":"Human Resources","aliases":["talent acquisition"]},
    {"canonical_name":"Onboarding","category":"Human Resources","aliases":[]},
    {"canonical_name":"Payroll Management","category":"Human Resources","aliases":["payroll"]}
  ]
})";

// ============================================================================
// Singleton engine state (loaded once, reused across calls for performance)
// ============================================================================
struct EngineState {
    SkillTaxonomy            taxonomy;
    std::unique_ptr<SkillEngine>         skill_engine;
    std::unique_ptr<ResumeParser>        parser;
    std::unique_ptr<XGBoostRanker>       ranker;
    std::unique_ptr<RetrievalFeatureExtractor> retrieval;
    std::unique_ptr<ExplanationEngine>   explainer;
    bool                     initialized{false};
};

static EngineState g_state;
static std::mutex  g_mutex;

// ---------------------------------------------------------------------------
// load_taxonomy  — from file or bundled default
// ---------------------------------------------------------------------------
static SkillTaxonomy load_taxonomy(const std::string& path) {
    // Try to load from provided path
    if (!path.empty()) {
        std::ifstream f(path);
        if (f.good()) {
            try {
                json j;
                f >> j;
                SkillTaxonomy tax;
                tax.version = j.value("version", "");
                for (const auto& cat : j["categories"]) tax.categories.push_back(cat);
                for (const auto& sk : j["skills"]) {
                    TaxonomyEntry e;
                    e.canonical_name = sk.value("canonical_name", "");
                    e.category       = sk.value("category", "");
                    if (sk.contains("aliases"))
                        for (const auto& a : sk["aliases"]) e.aliases.push_back(a.get<std::string>());
                    if (!e.canonical_name.empty()) tax.skills.push_back(std::move(e));
                }
                tax.build_index();
                return tax;
            } catch (...) {}
        }
    }

    // Fall back to bundled default
    json j = json::parse(DEFAULT_TAXONOMY_JSON);
    SkillTaxonomy tax;
    tax.version = j.value("version", "2.0.0-bundled");
    for (const auto& cat : j["categories"]) tax.categories.push_back(cat);
    for (const auto& sk : j["skills"]) {
        TaxonomyEntry e;
        e.canonical_name = sk.value("canonical_name", "");
        e.category       = sk.value("category", "");
        if (sk.contains("aliases"))
            for (const auto& a : sk["aliases"]) e.aliases.push_back(a.get<std::string>());
        if (!e.canonical_name.empty()) tax.skills.push_back(std::move(e));
    }
    tax.build_index();
    return tax;
}

// ---------------------------------------------------------------------------
// initialize_engine  — called once
// ---------------------------------------------------------------------------
static void initialize_engine(const std::string& taxonomy_path,
                               const std::string& model_path)
{
    g_state.taxonomy     = load_taxonomy(taxonomy_path);
    g_state.skill_engine = std::make_unique<SkillEngine>(g_state.taxonomy);
    g_state.parser       = std::make_unique<ResumeParser>();
    g_state.ranker       = std::make_unique<XGBoostRanker>(model_path);
    g_state.retrieval    = std::make_unique<RetrievalFeatureExtractor>();
    g_state.explainer    = std::make_unique<ExplanationEngine>();
    g_state.initialized  = true;
}

// ---------------------------------------------------------------------------
// score_impl  — the real scoring logic
// ---------------------------------------------------------------------------
static json score_impl(const json& req) {
    std::string resume_text = req.value("resume_text", "");
    std::string jd_text     = req.value("jd_text", "");
    std::string taxonomy_path = req.value("taxonomy_path", "data/configs/skill_taxonomy.json");
    std::string model_path    = req.value("model_path", "models/xgboost_model.json");

    if (resume_text.empty()) throw std::runtime_error("resume_text is empty");
    if (jd_text.empty())     throw std::runtime_error("jd_text is empty");

    // Parse embeddings
    std::vector<float> resume_emb, jd_emb;
    if (req.contains("resume_embedding") && req["resume_embedding"].is_array()) {
        for (auto& v : req["resume_embedding"]) resume_emb.push_back(v.get<float>());
    }
    if (req.contains("jd_embedding") && req["jd_embedding"].is_array()) {
        for (auto& v : req["jd_embedding"]) jd_emb.push_back(v.get<float>());
    }

    // Initialize engine if first call or taxonomy path changed
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!g_state.initialized) {
            initialize_engine(taxonomy_path, model_path);
        }
    }

    // --- Step 1: Parse resume ---
    Resume resume = g_state.parser->parse(resume_text);

    // --- Step 2: Extract skills ---
    SkillExtractionResult cand_skills =
        g_state.skill_engine->extract(resume_text, resume.raw_skills);
    SkillExtractionResult jd_skills_result =
        g_state.skill_engine->extract(jd_text);

    // --- Step 3: Skill gap analysis ---
    SkillGapResult gap = g_state.skill_engine->gap_analysis(
        cand_skills.matched_skills, jd_skills_result.matched_skills);

    // --- Step 4: Feature engineering ---
    FeatureVector fv;

    // JD tech list (for project feature extractor)
    std::vector<std::string> jd_techs;
    for (const auto& s : jd_skills_result.matched_skills) jd_techs.push_back(s.canonical_name);

    ExperienceFeatureExtractor::extract(resume, jd_text, fv);
    EducationFeatureExtractor::extract(resume, jd_text, fv);
    ProjectFeatureExtractor::extract(resume, jd_text, jd_techs, fv);
    CertificationFeatureExtractor::extract(resume, jd_text, fv);
    std::vector<std::string> candidate_skill_names;
    for (const auto& skill : cand_skills.matched_skills) candidate_skill_names.push_back(skill.canonical_name);
    ResumeQualityExtractor::extract(resume, fv, candidate_skill_names);
    SkillsFeatureExtractor::extract(cand_skills, jd_skills_result, gap, fv);
    g_state.retrieval->extract(resume_text, jd_text, resume_emb, jd_emb, fv);

    fv.fill_missing();

    // --- Step 5: Rank ---
    double probability = g_state.ranker->predict(fv);
    double overall_score = std::round(probability * 1000.0) / 10.0; // → X.X%

    // --- Step 6: Category scores ---
    CategoryScores cat = CategoryScoreComputer::compute(fv);

    // --- Step 7: Explain ---
    ExplanationEngine::ExplanationResult explanation =
        g_state.explainer->explain(fv, cat, gap);

    // --- Step 8: Serialize ---
    json result;
    result["overall_score"] = overall_score;
    result["scores"] = {
        {"skills",         std::round(cat.skills * 10.0) / 10.0},
        {"experience",     std::round(cat.experience * 10.0) / 10.0},
        {"education",      std::round(cat.education * 10.0) / 10.0},
        {"projects",       std::round(cat.projects * 10.0) / 10.0},
        {"semantic",       std::round(cat.semantic * 10.0) / 10.0},
        {"resume_quality", std::round(cat.resume_quality * 10.0) / 10.0}
    };

    result["matched_skills"]       = gap.matched_skills;
    result["missing_skills"]       = gap.missing_skills;

    json partial_arr = json::array();
    for (const auto& p : gap.partial_skills) {
        partial_arr.push_back({
            {"jd_skill",   p.jd_skill},
            {"matched_as", p.matched_as},
            {"confidence", std::round(p.confidence * 1000.0) / 1000.0}
        });
    }
    result["partial_skills"]       = partial_arr;
    result["top_positive_factors"] = explanation.positive_factors;
    result["top_negative_factors"] = explanation.negative_factors;
    result["ranking_method"]       = g_state.ranker->is_model_loaded() ? "xgboost" : "linear_fallback";

    // Debug: feature vector (optional)
    json fv_json = json::object();
    for (const auto& [k, v] : fv.features) {
        fv_json[k] = std::round(v * 10000.0) / 10000.0;
    }
    result["feature_vector"] = fv_json;
    result["error"] = nullptr;

    return result;
}

// ============================================================================
// C-linkage entry points
// ============================================================================

extern "C" {

TM_API const char* engine_score(const char* request_json) {
    std::string response_str;
    try {
        if (!request_json) {
            response_str = R"({"error":"request_json is null"})";
        } else {
            json req = json::parse(request_json);
            json result = score_impl(req);
            response_str = result.dump();
        }
    } catch (const std::exception& e) {
        json err;
        err["error"]         = std::string(e.what());
        err["overall_score"] = 0.0;
        err["scores"]        = {{"skills",0},{"experience",0},{"education",0},
                                 {"projects",0},{"semantic",0},{"resume_quality",0}};
        err["matched_skills"]       = json::array();
        err["missing_skills"]       = json::array();
        err["partial_skills"]       = json::array();
        err["top_positive_factors"] = json::array();
        err["top_negative_factors"] = json::array();
        response_str = err.dump();
    } catch (...) {
        response_str = R"({"error":"unknown exception in engine_score"})";
    }

    // Allocate heap string; caller must call engine_free()
    char* out = new char[response_str.size() + 1];
    std::memcpy(out, response_str.c_str(), response_str.size() + 1);
    return out;
}

TM_API void engine_free(const char* ptr) {
    delete[] ptr;
}

TM_API const char* engine_version() {
    return ENGINE_VERSION;
}

} // extern "C"
