const API_URL = 'https://talentmatch-ai-jwqd.onrender.com/api/score';

document.addEventListener('DOMContentLoaded', () => {
  const scoreForm = document.getElementById('scoreForm');
  const resumeUpload = document.getElementById('resumeUpload');
  const jobDescriptionInput = document.getElementById('jobDescription');
  const submitBtn = document.getElementById('submitBtn');
  const btnText = document.querySelector('.btn-text');
  const inputSection = document.getElementById('inputSection');
  const resultsSection = document.getElementById('resultsSection');
  const resetBtn = document.getElementById('resetBtn');
  const scoreCirclePath = document.getElementById('scoreCirclePath');
  const scoreValue = document.getElementById('scoreValue');
  const toast = document.getElementById('toast');
  const charCountDisplay = document.getElementById('charCount');
  const autoExtractBtn = document.getElementById('autoExtractBtn');

  // Profile elements
  const fileUploadGroup = document.getElementById('fileUploadGroup');
  const profileStatusIcon = document.getElementById('profileStatusIcon');
  const profileStatusText = document.getElementById('profileStatusText');
  const saveProfileBtn = document.getElementById('saveProfileBtn');
  const clearProfileBtn = document.getElementById('clearProfileBtn');

  let savedResumeText = null;

  // Load profile on start
  chrome.storage.local.get(['resumeText'], (result) => {
    if (result.resumeText) {
      setProfileActive(result.resumeText);
    }
  });

  function setProfileActive(text) {
    savedResumeText = text;
    profileStatusIcon.textContent = '✅';
    profileStatusText.textContent = 'Profile saved';
    fileUploadGroup.style.display = 'none';
    clearProfileBtn.style.display = 'inline-block';
    saveProfileBtn.textContent = 'Update Profile';
  }

  clearProfileBtn.addEventListener('click', () => {
    chrome.storage.local.remove(['resumeText'], () => {
      savedResumeText = null;
      profileStatusIcon.textContent = '❌';
      profileStatusText.textContent = 'No resume saved';
      fileUploadGroup.style.display = 'block';
      clearProfileBtn.style.display = 'none';
      saveProfileBtn.textContent = 'Save Page as Resume';
      resumeUpload.value = '';
    });
  });

  saveProfileBtn.addEventListener('click', async () => {
    try {
      let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) return;
      
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractTextFromPage
      }, (results) => {
        if (chrome.runtime.lastError) {
          showToast("Error: " + chrome.runtime.lastError.message);
          return;
        }
        if (results && results[0] && results[0].result) {
          const text = results[0].result;
          if (text.startsWith && text.startsWith("ERROR:")) {
             showToast("Extract Error: " + text.substring(0, 50));
             return;
          }
          if (text.length > 50) {
             chrome.storage.local.set({ resumeText: text }, () => {
               setProfileActive(text);
               showToast("Resume profile saved successfully!");
             });
          } else {
             showToast("Not enough text on page to save.");
          }
        } else {
          showToast("Failed to extract text from this page.");
        }
      });
    } catch (e) {
      showToast("Error saving profile: " + e.message);
    }
  });

  // Try to auto-extract JD on load
  autoExtractJD();

  autoExtractBtn.addEventListener('click', autoExtractJD);

  jobDescriptionInput.addEventListener('input', (e) => {
    charCountDisplay.textContent = `${e.target.value.length} / 15000`;
  });

  scoreForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const file = resumeUpload.files[0];
    const jdText = jobDescriptionInput.value;

    if (!savedResumeText && !file) {
      showToast("Please provide a PDF or save a profile first.");
      return;
    }
    
    if (!jdText) {
      showToast("Please provide a Job Description.");
      return;
    }

    if (!savedResumeText && file && file.size > 2 * 1024 * 1024) {
      showToast("File is too large! Please upload a PDF under 2MB.");
      return;
    }

    submitBtn.disabled = true;
    btnText.textContent = "Analyzing...";

    const formData = new FormData();
    if (savedResumeText) {
      formData.append('resume_text', savedResumeText);
    } else {
      formData.append('pdf_file', file);
    }
    formData.append('job_description', jdText.substring(0, 15000)); // enforce limit

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Server error occurred');
      }

      const data = await response.json();
      
      const rememberResume = document.getElementById('rememberResume');
      if (!savedResumeText && rememberResume && rememberResume.checked && data.parsed_resume && data.parsed_resume.raw_extracted_text) {
        const text = data.parsed_resume.raw_extracted_text;
        chrome.storage.local.set({ resumeText: text }, () => {
          setProfileActive(text);
          showToast("Perfectly extracted profile saved from PDF!");
        });
      }

      showResults(data);
    } catch (error) {
      showToast(error.message);
    } finally {
      submitBtn.disabled = false;
      btnText.textContent = "Analyze Match";
    }
  });

  resetBtn.addEventListener('click', () => {
    scoreForm.reset();
    resultsSection.style.display = 'none';
    inputSection.style.display = 'block';
    scoreCirclePath.setAttribute('stroke-dasharray', '0, 100');
    
    const semanticCirclePath = document.getElementById('semanticCirclePath');
    if (semanticCirclePath) semanticCirclePath.setAttribute('stroke-dasharray', '0, 100');
    
    const matchSummaryContainer = document.getElementById('matchSummaryContainer');
    if (matchSummaryContainer) matchSummaryContainer.style.display = 'none';
    
    const extRedFlagsContainer = document.getElementById('extRedFlagsContainer');
    if (extRedFlagsContainer) extRedFlagsContainer.style.display = 'none';

    charCountDisplay.textContent = '0 / 15000';
    autoExtractJD(); // Try to get text again
  });

  const visitWebsiteBtn = document.getElementById('visitWebsiteBtn');
  if (visitWebsiteBtn) {
    visitWebsiteBtn.addEventListener('click', () => {
      chrome.tabs.create({ url: 'https://talentmatch-ai-jwqd.onrender.com/' });
    });
  }

  function showResults(data) {
    const score = data.overall_score || data.score || 0;
    const percentage = Math.round(score);
    
    const semanticScore = (data.scores && data.scores.semantic) || 0;
    const semanticPercentage = Math.round(semanticScore);
    
    inputSection.style.display = 'none';
    resultsSection.style.display = 'block';

    const semanticCirclePath = document.getElementById('semanticCirclePath');
    const semanticValue = document.getElementById('semanticValue');

    const extRedFlagsContainer = document.getElementById('extRedFlagsContainer');
    const extRedFlagsList = document.getElementById('extRedFlagsList');
    const flags = [];
    if (data.feature_vector) {
      if (data.feature_vector.job_hopper_flag > 0.5) flags.push("Job-Hopping Detected (3+ short tenures)");
      if (data.feature_vector.keyword_stuffing_penalty > 0.5) flags.push("Keyword Stuffing Detected (Extremely high skill density)");
      if (data.feature_vector.overqualified_flag > 0.5) flags.push("Over-Qualification Risk (Seniority exceeds role requirements)");
    }
    if (flags.length > 0 && extRedFlagsContainer) {
      extRedFlagsList.innerHTML = flags.map(f => `<li>${f}</li>`).join('');
      extRedFlagsContainer.style.display = 'block';
    } else if (extRedFlagsContainer) {
      extRedFlagsContainer.style.display = 'none';
    }
    
    setTimeout(() => {
      scoreCirclePath.setAttribute('stroke-dasharray', `${percentage}, 100`);
      if (semanticCirclePath) semanticCirclePath.setAttribute('stroke-dasharray', `${semanticPercentage}, 100`);
      
      if (percentage >= 75) {
        scoreCirclePath.style.stroke = 'var(--success-color)';
      } else if (percentage >= 50) {
        scoreCirclePath.style.stroke = 'var(--accent-color)';
      } else {
        scoreCirclePath.style.stroke = 'var(--danger-color)';
      }

      if (semanticCirclePath) {
        if (semanticPercentage >= 75) {
          semanticCirclePath.style.stroke = 'var(--success-color)';
        } else if (semanticPercentage >= 50) {
          semanticCirclePath.style.stroke = 'var(--accent-color)';
        } else {
          semanticCirclePath.style.stroke = 'var(--danger-color)';
        }
      }
    }, 100);

    animateValue(scoreValue, 0, percentage, 1500);
    if (semanticValue) animateValue(semanticValue, 0, semanticPercentage, 1500);

    // Profile Highlights
    const parsed = data.parsed_resume;
    if (parsed) {
      document.getElementById('candidateProfile').style.display = 'block';
      const name = (parsed.contact && parsed.contact.full_name) ? parsed.contact.full_name : "Unknown Candidate";
      document.getElementById('candidateName').textContent = name;
      document.getElementById('candidateEmail').textContent = (parsed.contact && parsed.contact.email) ? parsed.contact.email : "No email provided";
      const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || "?";
      document.getElementById('candidateInitials').textContent = initials;
      document.getElementById('candidateSummary').textContent = parsed.summary || "No professional summary provided.";
      
      const expCount = parsed.experience ? parsed.experience.length : 0;
      document.getElementById('perkExperience').textContent = `${expCount} role${expCount === 1 ? '' : 's'}`;
      
      const eduCount = parsed.education ? parsed.education.length : 0;
      document.getElementById('perkEducation').textContent = `${eduCount} degree${eduCount === 1 ? '' : 's'}`;
      
      const projCount = parsed.projects ? parsed.projects.length : 0;
      document.getElementById('perkProjects').textContent = `${projCount} project${projCount === 1 ? '' : 's'}`;
    } else {
      document.getElementById('candidateProfile').style.display = 'none';
    }

    // Strengths & Improvements
    const analysisGrid = document.getElementById('analysisGrid');
    const strengthsList = document.getElementById('strengthsList');
    const improvementsList = document.getElementById('improvementsList');
    const strengths = data.top_positive_factors || [];
    const improvements = data.top_negative_factors || [];
    
    if (strengths.length > 0 || improvements.length > 0) {
      strengthsList.innerHTML = strengths.map(s => `<li><span class="check-icon">✓</span> ${s}</li>`).join('') || '<li>No specific strengths identified.</li>';
      improvementsList.innerHTML = improvements.map(s => `<li><span class="x-icon">✗</span> ${s}</li>`).join('') || '<li>No specific areas for improvement identified.</li>';
      analysisGrid.style.display = 'grid';
    } else {
      analysisGrid.style.display = 'none';
    }

    // Skills
    const skillsContainer = document.getElementById('skillsContainer');
    const matchedSkillsDiv = document.getElementById('matchedSkills');
    const missingSkillsDiv = document.getElementById('missingSkills');
    
    const formatSkill = (skill) => {
        if (!skill) return "";
        const known = {'c': 'C', 'r': 'R', 'cpp': 'C++', 'c++': 'C++', 'c#': 'C#', 'javascript': 'JavaScript', 'typescript': 'TypeScript', 'html': 'HTML', 'css': 'CSS', 'php': 'PHP', 'sql': 'SQL', 'mysql': 'MySQL', 'postgresql': 'PostgreSQL', 'aws': 'AWS', 'gcp': 'GCP', 'api': 'API', 'ui': 'UI', 'ux': 'UX', 'react': 'React', 'node': 'Node.js'};
        if (known[skill.toLowerCase()]) return known[skill.toLowerCase()];
        return skill.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
    };

    if (data.matched_skills || data.missing_skills) {
      skillsContainer.style.display = 'block';
      const matched = data.matched_skills || [];
      const missing = data.missing_skills || [];
      matchedSkillsDiv.innerHTML = matched.map(s => `<span class="skill-tag matched">${formatSkill(s)}</span>`).join('') || '<span class="skill-tag empty">None found</span>';
      missingSkillsDiv.innerHTML = missing.map(s => `<span class="skill-tag missing">${formatSkill(s)}</span>`).join('') || '<span class="skill-tag empty">None missing</span>';
    } else {
      skillsContainer.style.display = 'none';
    }

    // AI Match Summary
    const matchSummaryContainer = document.getElementById('matchSummaryContainer');
    const matchSummaryText = document.getElementById('matchSummaryText');
    if (data.match_summary) {
      matchSummaryText.textContent = data.match_summary;
      if(matchSummaryContainer) matchSummaryContainer.style.display = 'block';
    } else {
      if(matchSummaryContainer) matchSummaryContainer.style.display = 'none';
    }
  }

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

  // --- Auto-Extraction Logic ---
  async function autoExtractJD() {
    try {
      let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) return;
      
      // Inject script to extract text
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractTextFromPage
      }, (results) => {
        if (chrome.runtime.lastError) {
          console.error("Injection error:", chrome.runtime.lastError.message);
          return;
        }
        if (results && results[0] && results[0].result) {
          const text = results[0].result;
          if (text.startsWith && text.startsWith("ERROR:")) {
             console.error(text);
             return;
          }
          if (text.length > 50) { // arbitrary minimum
             const smartText = smartExtractJD(text);
             jobDescriptionInput.value = smartText;
             charCountDisplay.textContent = `${smartText.length} / 15000`;
          }
        }
      });
    } catch (e) {
      console.log("Auto-extract failed:", e);
    }
  }

  // This runs IN THE CONTEXT OF THE WEBPAGE
  async function extractTextFromPage() {
    try {
      // 1. Google Docs specific extraction using the official Export API!
      if (window.location.hostname.includes('docs.google.com')) {
        const match = window.location.pathname.match(/\/d\/([a-zA-Z0-9-_]+)/);
        if (match && match[1]) {
          const docId = match[1];
          try {
            // Fetch the pristine text document directly from Google Docs
            const response = await fetch(`https://docs.google.com/document/d/${docId}/export?format=txt`);
            if (response.ok) {
              const text = await response.text();
              if (text && text.trim().length > 50) {
                return text.trim();
              }
            }
          } catch (e) {
            console.log("Failed to fetch doc text, falling back...", e);
          }
        }
        
        // Fallback if export fails
        let text = document.body ? document.body.innerText : "";
        if (!text) {
          const editor = document.querySelector('.kix-appview-editor') || document.querySelector('#kix-appview');
          if (editor) text = editor.innerText;
        }

        if (text) {
          const uiGarbage = [
            /FileEditViewInsertFormatTools.*?Help/g,
            /Normal text/g,
            /Calibri/g,
            /Arial/g,
            /Editing/g,
            /Show tabs and outlines/g,
            /Turn on screen reader support/g,
            /To enable screen reader support.*?Ctrl\+slash/g,
            /Banner hidden/g,
            /^[\s\d]+$/gm // Remove ruler numbers
          ];
          for (let regex of uiGarbage) {
            text = text.replace(regex, "");
          }
          return text.trim();
        }
      }

      // 2. Try to find common JD containers (LinkedIn, Indeed, etc)
      const selectors = [
        '#job-details', // LinkedIn split view
        '.jobs-description__content', // LinkedIn standalone
        '.jobs-search__job-details--container', // LinkedIn search right pane
        '.job-view-layout', // LinkedIn alternate
        '.job-description', 
        '#jobDescriptionText', // Indeed
        '.jobDescriptionContent',
        'div[data-testid="job-description"]' // Modern job boards
      ];
      
      for (let s of selectors) {
        const el = document.querySelector(s);
        if (el && el.innerText && el.innerText.length > 50) {
           return el.innerText.trim();
        }
      }
      
      // 3. Fallback: Just grab the body text
      if (document.body && document.body.innerText) {
        return document.body.innerText.trim();
      }
      return "";
    } catch (e) {
      return "ERROR: " + e.message;
    }
  }

  // Helper to find the most relevant 15000 characters of a JD
  function smartExtractJD(text) {
    if (text.length <= 15000) return text;
    
    const lowerText = text.toLowerCase();
    const keywords = [
      'requirements', 'qualifications', 'what you bring', 
      'what you need', 'skills', 'responsibilities', 'what you\'ll do'
    ];
    
    let bestIndex = -1;
    for (let kw of keywords) {
      let idx = lowerText.indexOf(kw);
      if (idx !== -1) {
        if (bestIndex === -1 || idx < bestIndex) {
           bestIndex = idx;
        }
      }
    }
    
    if (bestIndex !== -1) {
      // Start slightly before the keyword to capture the section header
      let start = Math.max(0, bestIndex - 50); 
      let extracted = text.substring(start, start + 15000);
      
      // Clean up broken words at the end
      let lastSpace = extracted.lastIndexOf(' ');
      if (lastSpace > 0) {
        extracted = extracted.substring(0, lastSpace);
      }
      return extracted.trim();
    }
    
    return text.substring(0, 15000);
  }
});
