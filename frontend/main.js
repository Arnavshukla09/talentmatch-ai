// API Configuration
const API_URL = 'https://talentmatch-ai-jwqd.onrender.com'; // Change for production

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

// Form submission
scoreForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const file = resumeUpload.files[0];
  const jdText = document.getElementById('jobDescription').value;

  if (!file || !jdText) {
    showToast("Please provide both a PDF and a Job Description.");
    return;
  }

  // Set loading state
  submitBtn.disabled = true;
  btnText.textContent = "Analyzing...";
  btnLoader.style.display = "block";

  const formData = new FormData();
  formData.append('pdf_file', file);
  formData.append('job_description', jdText);

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
    showResults(data);
  } catch (error) {
    showToast(error.message);
  } finally {
    // Reset loading state
    submitBtn.disabled = false;
    btnText.textContent = "Analyze Match";
    btnLoader.style.display = "none";
  }
});

// Display Results
function showResults(data) {
  const score = data.score;
  const percentage = Math.round(score * 100);
  
  // Transition UI
  inputSection.style.display = 'none';
  resultsSection.style.display = 'block';
  
  // Animate Circular Progress
  // stroke-dasharray format: "value, 100"
  setTimeout(() => {
    scoreCirclePath.setAttribute('stroke-dasharray', `${percentage}, 100`);
    
    // Set color based on score
    if (percentage >= 75) {
      scoreCirclePath.style.stroke = 'var(--success-color)';
    } else if (percentage >= 50) {
      scoreCirclePath.style.stroke = 'var(--accent-color)';
    } else {
      scoreCirclePath.style.stroke = 'var(--danger-color)';
    }
  }, 100);

  // Count up animation for number
  animateValue(scoreValue, 0, percentage, 1500);

  // Format explanation JSON
  explanationContent.textContent = JSON.stringify(data.explanation, null, 2);
}

// Reset UI
resetBtn.addEventListener('click', () => {
  scoreForm.reset();
  fileNameDisplay.textContent = '';
  resultsSection.style.display = 'none';
  inputSection.style.display = 'block';
  scoreCirclePath.setAttribute('stroke-dasharray', '0, 100');
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
