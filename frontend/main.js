// Escape untrusted API text before inserting it into HTML templates.
function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

// Theme toggle
const THEME_KEY = 'talentmatch-theme';
const themeToggleBtn = document.getElementById('themeToggle');

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
}

themeToggleBtn.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  applyTheme(current === 'light' ? 'dark' : 'light');
});

// API Configuration — relative path works on localhost AND Render
const API_URL = '/api/score';

// Elements
const scoreForm = document.getElementById('scoreForm');
const resumeUpload = document.getElementById('resumeUpload');
const dropArea = document.getElementById('dropArea');
const fileNameDisplay = document.getElementById('fileName');
const submitBtn = document.getElementById('submitBtn');
const btnText = document.querySelector('.btn-text');
const btnLoader = document.getElementById('btnLoader');
const inputSection = document.getElementById('inputSection');
const resultsSection = document.getElementById('resultsSection');
const resetBtn = document.getElementById('resetBtn');
const scoreCirclePath = document.getElementById('scoreCirclePath');
const scoreValue = document.getElementById('scoreValue');
const explanationContent = document.getElementById('explanationContent');
const toast = document.getElementById('toast');

// File input interactions
resumeUpload.addEventListener('change', (e) => {
  if (e.target.files.length > 0) {
    fileNameDisplay.textContent = e.target.files[0].name;
  } else {
    fileNameDisplay.textContent = '';
  }
});

// Drag and drop styles
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
  dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
  dropArea.addEventListener(eventName, () => dropArea.classList.add('drag-over'), false);
});

['dragleave', 'drop'].forEach(eventName => {
  dropArea.addEventListener(eventName, () => dropArea.classList.remove('drag-over'), false);
});

dropArea.addEventListener('drop', (e) => {
  let dt = e.dataTransfer;
  let files = dt.files;
  resumeUpload.files = files;
  
  if (files.length > 0) {
    fileNameDisplay.textContent = files[0].name;
  }
});

// Character Counter for JD
const jobDescriptionInput = document.getElementById('jobDescription');
const charCountDisplay = document.getElementById('charCount');

jobDescriptionInput.addEventListener('input', (e) => {
  const currentLength = e.target.value.length;
  charCountDisplay.textContent = `${currentLength} / 15000`;
});

const loadingTexts = [
  "Reading resume structure...",
  "Extracting skills and experience...",
  "Analyzing job description...",
  "Calculating semantic similarity...",
  "Evaluating ATS criteria...",
  "Finalizing match score..."
];
let loadingInterval;
let textIndex = 0;

// Form submission
scoreForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const file = resumeUpload.files[0];
  const jdText = jobDescriptionInput.value.trim();

  if (!file || !jdText) {
    showToast("Please provide both a PDF and a Job Description.");
    return;
  }

  // File size validation (limit to 2MB to save memory)
  if (file.size > 2 * 1024 * 1024) {
    showToast("File is too large! Please upload a PDF under 2MB.");
    return;
  }

  // Client-side length validation
  if (jdText.length > 15000) {
    showToast("Job Description is too long. Max 15000 characters.");
    return;
  }

  // Set loading state
  submitBtn.disabled = true;
  btnLoader.style.display = "block";
  textIndex = 0;
  btnText.textContent = loadingTexts[textIndex];
  
  loadingInterval = setInterval(() => {
    textIndex = (textIndex + 1) % loadingTexts.length;
    btnText.textContent = loadingTexts[textIndex];
  }, 2500);

  const formData = new FormData();
  formData.append('pdf_file', file);
  formData.append('job_description', jdText);

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      body: formData,
      signal: AbortSignal.timeout(120000),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Server error occurred');
    }

    const data = await response.json();
    showResults(data);
  } catch (error) {
    showToast(error.name === 'TimeoutError' ? 'The server took too long. Please try again.' : error.message);
  } finally {
    // Reset loading state
    clearInterval(loadingInterval);
    submitBtn.disabled = false;
    btnText.textContent = "Analyze Match";
    btnLoader.style.display = "none";
  }
});

// Display Results
function showResults(data) {
  const score = data.overall_score || 0;
  const percentage = Math.round(score);
  
  const semanticScore = (data.scores && data.scores.semantic) || 0;
  const semanticPercentage = Math.round(semanticScore);

  // Transition UI
  inputSection.style.display = 'none';
  resultsSection.style.display = 'block';
  
  const semanticCirclePath = document.getElementById('semanticCirclePath');
  const semanticValue = document.getElementById('semanticValue');

  // Animate Circular Progress
  setTimeout(() => {
    scoreCirclePath.setAttribute('stroke-dasharray', `${percentage}, 100`);
    semanticCirclePath.setAttribute('stroke-dasharray', `${semanticPercentage}, 100`);
    
    // Set color based on score
    if (percentage >= 75) {
      scoreCirclePath.style.stroke = 'var(--success-color)';
    } else if (percentage >= 50) {
      scoreCirclePath.style.stroke = 'var(--accent-color)';
    } else {
      scoreCirclePath.style.stroke = 'var(--danger-color)';
    }

    if (semanticPercentage >= 75) {
      semanticCirclePath.style.stroke = 'var(--success-color)';
    } else if (semanticPercentage >= 50) {
      semanticCirclePath.style.stroke = 'var(--accent-color)';
    } else {
      semanticCirclePath.style.stroke = 'var(--danger-color)';
    }
  }, 100);

  // Count up animation for number
  animateValue(scoreValue, 0, percentage, 1500);
  animateValue(semanticValue, 0, semanticPercentage, 1500);

  // Populate Candidate Highlights (Hidden since raw parsed_resume is not returned by the C++ engine)
  const parsed = data.parsed_resume;
  if (parsed) {
    document.getElementById('candidateProfile').style.display = 'block';
    const name = (parsed.contact && parsed.contact.full_name) ? parsed.contact.full_name : "Unknown Candidate";
    document.getElementById('candidateName').textContent = name;
    document.getElementById('candidateEmail').textContent = (parsed.contact && parsed.contact.email) ? parsed.contact.email : "No email provided";
    
    // Initials
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || "?";
    document.getElementById('candidateInitials').textContent = initials;
    
    // Summary
    document.getElementById('candidateSummary').textContent = parsed.summary || "No professional summary provided.";
    
    // Perks
    const expCount = parsed.experience ? parsed.experience.length : 0;
    document.getElementById('perkExperience').textContent = `${expCount} role${expCount === 1 ? '' : 's'}`;
    
    const eduCount = parsed.education ? parsed.education.length : 0;
    document.getElementById('perkEducation').textContent = `${eduCount} degree${eduCount === 1 ? '' : 's'}`;
    
    const projCount = parsed.projects ? parsed.projects.length : 0;
    document.getElementById('perkProjects').textContent = `${projCount} project${projCount === 1 ? '' : 's'}`;
  } else {
    document.getElementById('candidateProfile').style.display = 'none';
  }

  // Parse Analysis Grid (Strengths & Improvements)
  const analysisGrid = document.getElementById('analysisGrid');
  const strengthsList = document.getElementById('strengthsList');
  const improvementsList = document.getElementById('improvementsList');
  
  const strengths = data.top_positive_factors || [];
  const improvements = data.top_negative_factors || [];
  
  if (strengths.length > 0 || improvements.length > 0) {
    strengthsList.innerHTML = strengths.map(s => `<li><span class="check-icon">✓</span> ${escapeHTML(s)}</li>`).join('') || '<li>No specific strengths identified.</li>';
    improvementsList.innerHTML = improvements.map(s => `<li><span class="x-icon">✗</span> ${escapeHTML(s)}</li>`).join('') || '<li>No specific areas for improvement identified.</li>';
    analysisGrid.style.display = 'grid';
  } else {
    analysisGrid.style.display = 'none';
  }

  // Parse Skills
  const skillsContainer = document.getElementById('skillsContainer');
  const matchedSkillsDiv = document.getElementById('matchedSkills');
  const missingSkillsDiv = document.getElementById('missingSkills');
  
  const formatSkill = (skill) => {
      if (!skill) return "";
      const known = {
          'c': 'C', 'r': 'R', 'cpp': 'C++', 'c++': 'C++', 'c#': 'C#',
          'javascript': 'JavaScript', 'typescript': 'TypeScript', 'html': 'HTML',
          'css': 'CSS', 'php': 'PHP', 'sql': 'SQL', 'mysql': 'MySQL',
          'postgresql': 'PostgreSQL', 'aws': 'AWS', 'gcp': 'GCP',
          'api': 'API', 'ui': 'UI', 'ux': 'UX', 'react': 'React', 'node': 'Node.js'
      };
      if (known[skill.toLowerCase()]) return known[skill.toLowerCase()];
      return skill.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
  };

  if (data.matched_skills || data.missing_skills) {
    skillsContainer.style.display = 'block';
    const matched = data.matched_skills || [];
    const missing = data.missing_skills || [];
    
    matchedSkillsDiv.innerHTML = matched.map(s => `<span class="skill-tag matched">${escapeHTML(formatSkill(s))}</span>`).join('') || '<span class="skill-tag empty">None found</span>';
    missingSkillsDiv.innerHTML = missing.map(s => `<span class="skill-tag missing">${escapeHTML(formatSkill(s))}</span>`).join('') || '<span class="skill-tag empty">None missing</span>';
  } else {
    skillsContainer.style.display = 'none';
  }

  // --- AI Match Summary ---
  const matchSummaryContainer = document.getElementById('matchSummaryContainer');
  const matchSummaryText = document.getElementById('matchSummaryText');
  if (data.match_summary) {
    matchSummaryText.textContent = data.match_summary;
    if(matchSummaryContainer) matchSummaryContainer.style.display = 'block';
  } else {
    if(matchSummaryContainer) matchSummaryContainer.style.display = 'none';
  }

  // --- ATS Red Flags ---
  const redFlagsContainer = document.getElementById('redFlagsContainer');
  const redFlagsList = document.getElementById('redFlagsList');
  const flags = [];
  if (data.feature_vector) {
    if (data.feature_vector.job_hopper_flag > 0.5) flags.push("Job-Hopping Detected (3+ short tenures)");
    if (data.feature_vector.keyword_stuffing_penalty > 0.5) flags.push("Keyword Stuffing Detected (Extremely high skill density)");
    if (data.feature_vector.overqualified_flag > 0.5) flags.push("Over-Qualification Risk (Seniority exceeds role requirements)");
  }
  if (flags.length > 0 && redFlagsContainer) {
    redFlagsList.innerHTML = flags.map(f => `<li>${f}</li>`).join('');
    redFlagsContainer.style.display = 'block';
  } else if (redFlagsContainer) {
    redFlagsContainer.style.display = 'none';
  }

  // --- AI Suggestions ---
  const suggestionsContainer = document.getElementById('suggestionsContainer');
  const suggestionsList = document.getElementById('suggestionsList');

  if (data.suggestions && data.suggestions.length > 0) {
    suggestionsList.innerHTML = data.suggestions.map(s => {
      const priority = ['high', 'medium', 'low'].includes(s.priority) ? s.priority : 'medium';
      const priorityClass = `priority-${priority}`;
      const priorityLabel = priority.toUpperCase();
      return `
        <div class="suggestion-card">
          <div class="suggestion-card-top">
            <span class="suggestion-issue">⚠ ${escapeHTML(s.issue)}</span>
            <span class="suggestion-priority ${priorityClass}">${priorityLabel}</span>
          </div>
          <p class="suggestion-text">✨ ${escapeHTML(s.suggestion)}</p>
        </div>`;
    }).join('');
    if(suggestionsContainer) suggestionsContainer.style.display = 'block';
  } else {
    if(suggestionsContainer) suggestionsContainer.style.display = 'none';
  }

  // Format Developer Details as a Table
  const explanationContent = document.getElementById('explanationContent');
  if (data.feature_vector) {
    let tableHTML = `<table class="dev-table">
      <thead>
        <tr>
          <th>Feature Name</th>
          <th>Raw Value</th>
        </tr>
      </thead>
      <tbody>`;
    
    for (const [key, value] of Object.entries(data.feature_vector)) {
      const formattedValue = typeof value === 'number' ? parseFloat(value.toFixed(4)) : value;
      
      tableHTML += `
        <tr>
          <td>${escapeHTML(key)}</td>
          <td>${escapeHTML(formattedValue)}</td>
        </tr>`;
    }
    
    tableHTML += `</tbody></table>`;
    explanationContent.innerHTML = tableHTML;
  } else {
    explanationContent.textContent = "No detailed breakdown available.";
  }
}

// Reset UI
resetBtn.addEventListener('click', () => {
  scoreForm.reset();
  fileNameDisplay.textContent = '';
  charCountDisplay.textContent = '0 / 15000';
  resultsSection.style.display = 'none';
  inputSection.style.display = 'block';
  scoreCirclePath.setAttribute('stroke-dasharray', '0, 100');
  
  const semanticCirclePath = document.getElementById('semanticCirclePath');
  if (semanticCirclePath) {
    semanticCirclePath.setAttribute('stroke-dasharray', '0, 100');
  }

  const matchSummaryContainer = document.getElementById('matchSummaryContainer');
  if (matchSummaryContainer) matchSummaryContainer.style.display = 'none';

  const redFlagsContainer = document.getElementById('redFlagsContainer');
  if (redFlagsContainer) redFlagsContainer.style.display = 'none';

  const suggestionsContainer = document.getElementById('suggestionsContainer');
  if (suggestionsContainer) suggestionsContainer.style.display = 'none';
});

// Utilities
function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 4000);
}

function animateValue(obj, start, end, duration) {
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    obj.innerHTML = Math.floor(progress * (end - start) + start) + "%";
    if (progress < 1) {
      window.requestAnimationFrame(step);
    }
  };
  window.requestAnimationFrame(step);
}
