const { ipcRenderer } = require('electron');
const path = require('path');
const fs = require('fs');

// DOM Elements
const directoryInput = document.getElementById('directoryPath');
const browseBtn = document.getElementById('browseBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const loader = document.getElementById('loader');
const resultsContainer = document.getElementById('resultsContainer');
const fileTree = document.getElementById('fileTree');
const applyBtn = document.getElementById('applyBtn');
const messageContainer = document.getElementById('messageContainer');
const addDirBtn = document.getElementById('addDirBtn');
const expandAllBtn = document.getElementById('expandAllBtn');
const collapseAllBtn = document.getElementById('collapseAllBtn');
const resetBtn = document.getElementById('resetBtn');

// Add at the beginning of the file after existing DOM elements
const tabButtons = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

// Add after existing DOM elements
const renameDirectoryInput = document.getElementById('renameDirectoryPath');
const renameBrowseBtn = document.getElementById('renameBrowseBtn');
const generateNamesBtn = document.getElementById('generateNamesBtn');
const renamePreview = document.getElementById('renamePreview');
const renameApplyBtn = document.getElementById('renameApplyBtn');

// Store file structure data
let fileStructureData = null;

// Add at the beginning of the file
const DEBUG = true;

// Store the original file structure for reset functionality
let originalFileStructure = null;
// Track the current, potentially modified structure
let currentStructure = { files: [] };

// Store files for renaming
let filesToRename = [];
let generatedNames = {};
let selectedFiles = new Set();

// Create modal for adding directories
const modal = document.createElement('div');
modal.className = 'modal';
modal.innerHTML = `
  <div class="modal-content">
    <h3>Add New Directory</h3>
    <input type="text" id="newDirName" placeholder="Enter directory name">
    <div class="modal-buttons">
      <button id="cancelAddDir">Cancel</button>
      <button id="confirmAddDir">Add</button>
    </div>
  </div>
`;
document.body.appendChild(modal);

const newDirNameInput = document.getElementById('newDirName');
const cancelAddDirBtn = document.getElementById('cancelAddDir');
const confirmAddDirBtn = document.getElementById('confirmAddDir');

// Chat feature elements
const chatToggleBtn = document.getElementById('chatToggleBtn');
const chatInterface = document.getElementById('chatInterface');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');

// Add mode toggle event listener
const modeToggle = document.getElementById('modeToggle');
const limitsBox = document.querySelector('.limits-box');

// Add rate limit elements
const tokenLimitElement = document.querySelector('.token-limit');
const callLimitElement = document.querySelector('.call-limit');

// Add event listener for token usage updates
ipcRenderer.on('update-token-usage', (event, usage) => {
  if (tokenLimitElement) {
    tokenLimitElement.textContent = `${usage}/30,000 tokens`;
  }
});

ipcRenderer.on('update-call-usage', (event, usage) => {
  if (callLimitElement) {
    callLimitElement.textContent = `${usage}/10 calls`;
  }
});

// Function to update limits box visibility
function updateLimitsBoxVisibility() {
  if (modeToggle.checked) {
    limitsBox.classList.add('visible');
  } else {
    limitsBox.classList.remove('visible');
  }
}

// Initial state
updateLimitsBoxVisibility();

modeToggle.addEventListener('change', async (event) => {
  const isOnline = event.target.checked;
  await ipcRenderer.invoke('toggle-online-mode', isOnline);
  console.log(`Mode toggled to: ${isOnline ? 'ONLINE' : 'OFFLINE'}`);
  showMessage(`Mode set to ${isOnline ? 'ONLINE (OpenAI)' : 'OFFLINE (Local Models)'}`, 'info');
  updateLimitsBoxVisibility();
});

// Function to get current mode state
async function getCurrentMode() {
  return modeToggle.checked;
}

function debugLog(message, data) {
  if (DEBUG) {
    if (data) {
      console.log(`[DEBUG] ${message}`, data);
    } else {
      console.log(`[DEBUG] ${message}`);
    }
  }
}

// Event listeners
browseBtn.addEventListener('click', async () => {
  const directoryPath = await ipcRenderer.invoke('select-directory');
  if (directoryPath) {
    directoryInput.value = directoryPath;
    analyzeBtn.disabled = false;
  }
});

analyzeBtn.addEventListener('click', async () => {
  if (!validateAndAnalyzeDirectory(directoryInput.value.trim())) return;
  
  // Check rate limits before proceeding
  const canProceed = await checkRateLimits();
  if (!canProceed) return;
  
  // Increment call counter
  await ipcRenderer.invoke('update-call-usage');
  
  analyzeBtn.disabled = true;
  loader.style.display = 'flex';
  resultsContainer.style.display = 'none';
  showMessage('Analyzing files and generating structure...', 'info');
  
  try {
    const result = await ipcRenderer.invoke('analyze-directory', directoryInput.value.trim());
    console.log('Result from analyze-directory:', result);
    
    // Validate the result structure
    if (result) {
      // Check if result is a string (JSON)
      if (typeof result === 'string') {
        try {
          // Parse the JSON string
          const parsedResult = JSON.parse(result);
          if (parsedResult && parsedResult.files && Array.isArray(parsedResult.files)) {
            buildFileTree(parsedResult);
            resultsContainer.style.display = 'block';
            showMessage('Analysis complete!', 'success');
          } else {
            console.error('Invalid parsed result structure:', parsedResult);
            showMessage('Error: Invalid response format from server', 'error');
          }
        } catch (parseError) {
          console.error('Error parsing JSON result:', parseError);
          showMessage('Error: Failed to parse response from server', 'error');
        }
      } 
      // Check if it's an object with a files array
      else if (result.files && Array.isArray(result.files)) {
        buildFileTree(result);
        resultsContainer.style.display = 'block';
        showMessage('Analysis complete!', 'success');
      } 
      // If it's just an array, wrap it in an object
      else if (Array.isArray(result)) {
        buildFileTree({ files: result });
        resultsContainer.style.display = 'block';
        showMessage('Analysis complete!', 'success');
      } else {
        console.error('Invalid result structure:', result);
        showMessage('Error: Invalid response from server', 'error');
      }
    } else {
      showMessage('Error: No response from server', 'error');
    }
  } catch (error) {
    console.error('Error during analysis:', error);
    showMessage(`Error: ${error.message}`, 'error');
  } finally {
    analyzeBtn.disabled = false;
    loader.style.display = 'none';
  }
});

// Add input event listener to enable/disable analyze button
directoryInput.addEventListener('input', () => {
  analyzeBtn.disabled = !directoryInput.value.trim();
});

// Add keypress event listener for Enter key
directoryInput.addEventListener('keypress', (event) => {
  if (event.key === 'Enter' && directoryInput.value.trim()) {
    validateAndAnalyzeDirectory(directoryInput.value.trim());
  }
});

applyBtn.addEventListener('click', async () => {
  if (!fileStructureData) return;
  
  // Show loader
  loader.style.display = 'flex';
  applyBtn.disabled = true;
  
  try {
    // Call backend to apply changes with current structure
    const result = await ipcRenderer.invoke('apply-changes', fileStructureData);
    
    loader.style.display = 'none';
    applyBtn.disabled = false;
    
    if (result.success) {
      showMessage('File structure reorganization completed successfully!', 'success');
    } else {
      showMessage(`Error applying changes: ${result.message}`, 'error');
    }
  } catch (error) {
    loader.style.display = 'none';
    applyBtn.disabled = false;
    showMessage(`Error applying changes: ${error.message}`, 'error');
  }
});

// Build file tree visualization with drag-and-drop support
function buildFileTree(data) {
  console.log('buildFileTree called with data:', data);
  
  // Safety check for data
  if (!data) {
    console.error('No data provided to buildFileTree');
    showMessage('Error: No file structure data available', 'error');
    return;
  }
  
  // Ensure data.files exists and is an array
  if (!data.files || !Array.isArray(data.files)) {
    console.error('data.files is not an array:', data.files);
    showMessage('Error: Invalid file structure format', 'error');
    
    // Initialize with empty array if missing
    data = { files: [] };
  }
  
  // Store original data for reset
  originalFileStructure = JSON.parse(JSON.stringify(data));
  currentStructure = JSON.parse(JSON.stringify(data));
  
  fileTree.innerHTML = '';
  
  // Group files by directory
  const dirStructure = {};
  
  // Process all files
  for (const file of data.files) {
    const srcPath = file.src_path;
    const dstPath = file.dst_path;
    
    // Skip files with missing paths
    if (!srcPath || !dstPath) {
      console.warn('Skipping file with missing paths:', file);
      continue;
    }
    
    // Get destination directory
    const lastSlashIndex = dstPath.lastIndexOf('/');
    const dirPath = lastSlashIndex > 0 ? dstPath.substring(0, lastSlashIndex) : '';
    const fileName = lastSlashIndex > 0 ? dstPath.substring(lastSlashIndex + 1) : dstPath;
    
    // Add to directory structure
    if (!dirStructure[dirPath]) {
      dirStructure[dirPath] = [];
    }
    
    dirStructure[dirPath].push({
      originalPath: srcPath,
      newPath: dstPath,
      fileName: fileName
    });
  }
  
  // Create root element
  const rootElement = document.createElement('div');
  rootElement.textContent = 'ROOT';
  rootElement.className = 'folder open';
  rootElement.setAttribute('data-dir', 'ROOT');
  fileTree.appendChild(rootElement);
  
  // Create an unordered list for the root
  const rootList = document.createElement('ul');
  fileTree.appendChild(rootList);
  
  // Sort directories
  const sortedDirs = Object.keys(dirStructure).sort();
  
  // Add root files first
  if (dirStructure['']) {
    dirStructure[''].forEach(file => {
      const li = document.createElement('li');
      li.className = 'file';
      
      // Set the data-type attribute based on file extension
      const isImage = /\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(file.fileName);
      const isPdf = file.fileName.toLowerCase().endsWith('.pdf');
      li.setAttribute('data-type', isImage ? 'image' : (isPdf ? 'document' : 'other'));
      
      // Add icon and filename
      const icon = isImage ? '🖼️' : (isPdf ? '📕' : '');
      li.innerHTML = `${icon} ${file.fileName}`;
      
      li.title = `Original: ${file.originalPath}\nNew: ${file.newPath}`;
      li.setAttribute('data-src', file.originalPath);
      li.setAttribute('data-dst', file.newPath);
      li.setAttribute('data-filename', file.fileName);
      li.setAttribute('draggable', 'true');
      rootList.appendChild(li);
    });
  }
  
  // Add directories and their files
  sortedDirs.filter(dir => dir !== '').forEach(dir => {
    // Create directory element
    const dirLi = document.createElement('li');
    dirLi.className = 'folder open';
    
    // Use span for the text to prevent interference with the action buttons
    dirLi.innerHTML = `<span class="folder-name">${dir}</span>`;
    dirLi.setAttribute('data-dir', dir);
    
    // Add folder actions with stopPropagation
    const folderActions = document.createElement('span');
    folderActions.className = 'folder-actions';
    const removeBtn = document.createElement('button');
    removeBtn.className = 'remove-dir';
    removeBtn.innerHTML = '×';
    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      removeDirectory(dirLi);
    });
    folderActions.appendChild(removeBtn);
    dirLi.appendChild(folderActions);
    
    rootList.appendChild(dirLi);
    
    // Create list for files in this directory
    const dirFiles = document.createElement('ul');
    dirLi.appendChild(dirFiles);
    
    // Add files to this directory
    dirStructure[dir].forEach(file => {
      const fileLi = document.createElement('li');
      fileLi.className = 'file';
      
      // Set the data-type attribute based on file extension
      const isImage = /\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(file.fileName);
      const isPdf = file.fileName.toLowerCase().endsWith('.pdf');
      fileLi.setAttribute('data-type', isImage ? 'image' : (isPdf ? 'document' : 'other'));
      
      // Add icon and filename
      const icon = isImage ? '🖼️' : (isPdf ? '📕' : '');
      fileLi.innerHTML = `${icon} ${file.fileName}`;
      
      fileLi.title = `Original: ${file.originalPath}\nNew: ${file.newPath}`;
      fileLi.setAttribute('data-src', file.originalPath);
      fileLi.setAttribute('data-dst', file.newPath);
      fileLi.setAttribute('data-filename', file.fileName);
      fileLi.setAttribute('draggable', 'true');
      dirFiles.appendChild(fileLi);
    });
  });
  
  // Setup drag and drop
  setupDragAndDrop();
  
  // Add event listeners for folders
  document.querySelectorAll('.folder').forEach(folder => {
    folder.addEventListener('click', (e) => {
      // Don't toggle if clicking on action buttons
      if (e.target.closest('.folder-actions')) return;
      
      // Toggle folder
      folder.classList.toggle('open');
      const filesList = folder.querySelector('ul');
      if (filesList) {
        filesList.style.display = folder.classList.contains('open') ? 'block' : 'none';
      }
    });
  });
}

// Expand all folders
expandAllBtn.addEventListener('click', () => {
  document.querySelectorAll('.folder').forEach(folder => {
    folder.classList.add('open');
    const filesList = folder.querySelector('ul');
    if (filesList) {
      filesList.style.display = 'block';
    }
  });
});

// Collapse all folders
collapseAllBtn.addEventListener('click', () => {
  document.querySelectorAll('.folder').forEach(folder => {
    if (folder.getAttribute('data-dir') !== 'ROOT') {
      folder.classList.remove('open');
      const filesList = folder.querySelector('ul');
      if (filesList) {
        filesList.style.display = 'none';
      }
    }
  });
});

// Reset to original structure
resetBtn.addEventListener('click', () => {
  if (confirm('Reset to the original suggested file structure?')) {
    buildFileTree(originalFileStructure);
  }
});

// Setup drag and drop functionality
function setupDragAndDrop() {
  const draggableItems = document.querySelectorAll('.file[draggable="true"]');
  const dropTargets = document.querySelectorAll('.folder');
  
  let draggedItem = null;
  
  // Add event listeners for draggable items
  draggableItems.forEach(item => {
    item.addEventListener('dragstart', function() {
      draggedItem = this;
      setTimeout(() => this.classList.add('dragging'), 0);
    });
    
    item.addEventListener('dragend', function() {
      draggedItem = null;
      this.classList.remove('dragging');
      document.querySelectorAll('.drop-target').forEach(el => el.classList.remove('drop-target'));
    });
  });
  
  // Add event listeners for drop targets
  dropTargets.forEach(target => {
    target.addEventListener('dragover', function(e) {
      e.preventDefault();
      if (!this.classList.contains('drop-target')) {
        this.classList.add('drop-target');
      }
    });
    
    target.addEventListener('dragleave', function(e) {
      // Only remove the class if we're not hovering over any child element
      if (!this.contains(e.relatedTarget)) {
        this.classList.remove('drop-target');
      }
    });
    
    target.addEventListener('drop', function(e) {
      e.preventDefault();
      if (!draggedItem) return;
      
      const targetDir = this.getAttribute('data-dir');
      const targetList = this === fileTree.firstChild 
        ? fileTree.querySelector('ul') 
        : this.querySelector('ul');
      
      // Move the item in the DOM
      targetList.appendChild(draggedItem);
      
      // Add a subtle highlight instead of dark blue
      draggedItem.style.backgroundColor = '#f0f7ff';
      setTimeout(() => {
        draggedItem.style.backgroundColor = '';
      }, 800);
      
      // Update the path
      updateFilePathAfterDrag(draggedItem, targetDir);
      
      // Update file structure data
      updateFileStructure();
      
      this.classList.remove('drop-target');
    });
  });
}

// Update file path after dragging to a new directory
function updateFilePathAfterDrag(fileElement, newDir) {
  const fileName = fileElement.getAttribute('data-filename') || fileElement.textContent.trim();
  const srcPath = fileElement.getAttribute('data-src');
  let newPath;
  
  if (newDir === 'ROOT') {
    newPath = fileName;
  } else {
    newPath = `${newDir}/${fileName}`;
  }
  
  fileElement.setAttribute('data-dst', newPath);
  fileElement.title = `Original: ${srcPath}\nNew: ${newPath}`;
}

// Update the file structure based on current UI
function updateFileStructure() {
  const updatedFiles = [];
  
  // Get all files
  document.querySelectorAll('.file').forEach(file => {
    const srcPath = file.getAttribute('data-src');
    const dstPath = file.getAttribute('data-dst');
    
    updatedFiles.push({
      src_path: srcPath,
      dst_path: dstPath
    });
  });
  
  // Update current structure
  currentStructure = { files: updatedFiles };
  fileStructureData = currentStructure;
  
  debugLog("Updated file structure:", currentStructure);
}

// Show message
function showMessage(message, type) {
  messageContainer.innerHTML = message;
  messageContainer.className = `message-container ${type}`;
}

// Show modal for adding directory
addDirBtn.addEventListener('click', () => {
  newDirNameInput.value = '';
  modal.style.display = 'block';
});

// Hide modal
cancelAddDirBtn.addEventListener('click', () => {
  modal.style.display = 'none';
});

// Add new directory
confirmAddDirBtn.addEventListener('click', () => {
  const dirName = newDirNameInput.value.trim();
  if (dirName) {
    // Add the new directory to the structure
    addNewDirectory(dirName);
    modal.style.display = 'none';
  }
});

// Handle clicks outside the modal to close it
window.addEventListener('click', (event) => {
  if (event.target === modal) {
    modal.style.display = 'none';
  }
});

// Add a new directory to the structure
function addNewDirectory(dirName) {
  // Update UI
  const rootList = fileTree.querySelector('ul');
  const dirLi = document.createElement('li');
  dirLi.className = 'folder';
  dirLi.innerHTML = `<span class="folder-name">${dirName}</span>`;
  dirLi.setAttribute('data-dir', dirName);
  
  // Add folder actions with stopPropagation
  const folderActions = document.createElement('span');
  folderActions.className = 'folder-actions';
  const removeBtn = document.createElement('button');
  removeBtn.className = 'remove-dir';
  removeBtn.innerHTML = '×';
  removeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    removeDirectory(dirLi);
  });
  folderActions.appendChild(removeBtn);
  dirLi.appendChild(folderActions);
  
  // Add the directory's file list
  const dirFiles = document.createElement('ul');
  dirLi.appendChild(dirFiles);
  rootList.appendChild(dirLi);
  
  // Setup drag and drop for the new directory
  setupDragAndDrop();
  
  // Add event listener for folder expansion/collapse
  dirLi.addEventListener('click', (e) => {
    if (e.target.closest('.folder-actions')) return;
    
    dirLi.classList.toggle('open');
    const filesList = dirLi.querySelector('ul');
    if (filesList) {
      filesList.style.display = dirLi.classList.contains('open') ? 'block' : 'none';
    }
  });
}

// Remove a directory
function removeDirectory(dirElement) {
  // Highlight the directory being removed
  dirElement.style.backgroundColor = '#ffebee';
  dirElement.style.borderColor = '#ffcdd2';
  
  // Check if directory has files
  const filesList = dirElement.querySelector('ul');
  const files = filesList ? filesList.querySelectorAll('li.file') : [];
  
  if (files.length > 0) {
    if (!confirm(`Directory "${dirElement.getAttribute('data-dir')}" contains ${files.length} files. Move them to the root directory?`)) {
      // Reset the highlighting if cancelled
      dirElement.style.backgroundColor = '';
      dirElement.style.borderColor = '';
      return;
    }
    
    // Move files to root
    const rootList = fileTree.querySelector('ul');
    
    // Animate files being moved to root
    files.forEach(file => {
      const clone = file.cloneNode(true);
      rootList.appendChild(clone);
      
      // Add animation to highlight the moved files
      clone.style.backgroundColor = '#e8f5e9';
      setTimeout(() => {
        clone.style.backgroundColor = '';
      }, 1000);
      
      updateFilePathAfterDrag(clone, 'ROOT');
    });
  }
  
  // Add a quick fade-out animation
  dirElement.style.transition = 'opacity 0.3s, transform 0.3s';
  dirElement.style.opacity = '0';
  dirElement.style.transform = 'translateX(20px)';
  
  // Remove the directory from the UI after animation
  setTimeout(() => {
    dirElement.remove();
    // Update the data structure
    updateFileStructure();
  }, 300);
}

// Remove or simplify the getFileIcon function since it's no longer needed
function getFileIcon(fileName) {
  return ''; // Return empty string since we're using CSS for icons
}

// Add tab switching functionality
tabButtons.forEach(button => {
  button.addEventListener('click', () => {
    // Remove active class from all buttons and contents
    tabButtons.forEach(btn => btn.classList.remove('active'));
    tabContents.forEach(content => content.classList.remove('active'));
    
    // Add active class to clicked button and corresponding content
    button.classList.add('active');
    const tabId = button.getAttribute('data-tab');
    document.getElementById(tabId).classList.add('active');
  });
});

// Add IPC listeners for rate limit updates
ipcRenderer.on('update-token-usage', (event, usage) => {
  tokenLimitElement.textContent = `${usage}/30,000 tokens`;
});

ipcRenderer.on('update-call-usage', (event, usage) => {
  callLimitElement.textContent = `${usage}/10 calls`;
});

// Add function to check rate limits before operations
async function checkRateLimits() {
  const limits = await ipcRenderer.invoke('check-rate-limits');
  if (!limits.canProceed) {
    showMessage(`Rate limit reached! ${limits.tokenUsage}/${limits.tokenLimit} tokens and ${limits.callUsage}/${limits.callLimit} calls used.`, 'error');
    return false;
  }
  return true;
}

// Update analyze directory function
async function validateAndAnalyzeDirectory(path) {
  if (!path) return;
  
  try {
    // Check rate limits if in online mode
    if (modeToggle.checked) {
      const canProceed = await checkRateLimits();
      if (!canProceed) return;
    }
    
    // First validate if the directory exists
    const isValid = await ipcRenderer.invoke('validate-directory', path);
    
    if (!isValid) {
      showMessage('Please enter a valid directory path', 'error');
      return;
    }
    
    const currentMode = await getCurrentMode();
    console.log(`Starting analysis with mode: ${currentMode ? 'ONLINE' : 'OFFLINE'}`);
    
    // Show loader
    loader.style.display = 'flex';
    resultsContainer.style.display = 'none';
    messageContainer.innerHTML = '';
    
    debugLog(`Starting analysis for directory: ${path}`);
    debugLog(`Current mode: ${currentMode ? 'ONLINE' : 'OFFLINE'}`);
    
    // Check if test.json exists in the project root directory
    const testJsonExists = await ipcRenderer.invoke('check-test-json');
    
    let startTime = performance.now();
    let rawData;
    
    if (testJsonExists) {
      // Use test.json instead of running analysis
      debugLog('Found test.json in project root, using it instead of running full analysis');
      rawData = await ipcRenderer.invoke('read-test-json');
    } else {
      // Call backend to analyze directory as normal
      debugLog('No test.json found in project root, running full analysis');
      rawData = await ipcRenderer.invoke('analyze-directory', path);
    }
    
    const endTime = performance.now();
    debugLog(`Process completed in ${(endTime - startTime) / 1000} seconds`);
    debugLog("Raw data received:", rawData);
    
    // Ensure we have a valid data structure
    if (!rawData) {
      showMessage('Error: No data received from analysis', 'error');
      loader.style.display = 'none';
      return false;
    }
    
    // Convert from string to object if necessary
    if (typeof rawData === 'string') {
      try {
        rawData = JSON.parse(rawData);
        debugLog("Parsed JSON data:", rawData);
      } catch (parseError) {
        debugLog("Failed to parse JSON:", parseError);
        showMessage('Error: Invalid response format from server', 'error');
        loader.style.display = 'none';
        return false;
      }
    }
    
    // Ensure we have a valid files array
    if (!rawData.files && Array.isArray(rawData)) {
      // If rawData is an array, assume it's the files array
      fileStructureData = { files: rawData };
    } else if (rawData.files && Array.isArray(rawData.files)) {
      // If rawData has a files property that's an array, use it as is
      fileStructureData = rawData;
    } else {
      // Default to an empty files array
      debugLog("Invalid data structure, defaulting to empty files array");
      fileStructureData = { files: [] };
      showMessage('Warning: No valid files found in analysis result', 'error');
    }
    
    debugLog("Processed file structure data:", fileStructureData);
    
    // Build the file tree visualization
    buildFileTree(fileStructureData);
    
    // Hide loader and show results
    loader.style.display = 'none';
    resultsContainer.style.display = 'block';
    
    return true;
  } catch (error) {
    debugLog("Error during analysis:", error);
    loader.style.display = 'none';
    showMessage(`Error analyzing directory: ${error.message}`, 'error');
    return false;
  }
}

// Toggle chat interface
chatToggleBtn.addEventListener('click', () => {
  chatInterface.classList.toggle('hidden');
  if (!chatInterface.classList.contains('hidden')) {
    chatInput.focus();
  }
});

// Send message when clicking the send button
chatSendBtn.addEventListener('click', sendChatMessage);

// Send message when pressing Enter
chatInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    sendChatMessage();
  }
});

// Function to send a message and get a response
async function sendChatMessage() {
  const message = chatInput.value.trim();
  if (!message) return;

  // Disable send button and input while awaiting response
  chatSendBtn.disabled = true;
  chatInput.disabled = true;

  // Add user message to chat
  addMessageToChat(message, 'user');
  chatInput.value = '';

  // Show thinking indicator
  const thinkingId = addThinkingIndicator();

  try {
    // Send to backend and get response
    const response = await ipcRenderer.invoke('chat-query', {
      message: message,
      currentFileStructure: currentStructure
    });

    // Remove thinking indicator
    removeThinkingIndicator(thinkingId);

    // Add assistant response
    console.log("[DEBUG] Response from chat-query:", response);
    addMessageToChat(response.message, 'assistant');

    // Update file structure if needed
    if (response.updatedFileStructure) {
      currentStructure = response.updatedFileStructure;
      buildFileTree(currentStructure);
      showMessage('File structure updated based on your request', 'success');
    }
  } catch (error) {
    // Remove thinking indicator
    removeThinkingIndicator(thinkingId);

    // Show error message
    addMessageToChat('Sorry, I encountered an error processing your request. Please try again.', 'assistant');
    console.error('Chat error:', error);
  } finally {
    // Re-enable send button and input
    chatSendBtn.disabled = false;
    chatInput.disabled = false;
    chatInput.focus();
  }
}

// Add a message to the chat interface
function addMessageToChat(message, sender) {
  const messageElement = document.createElement('div');
  messageElement.classList.add('chat-message');
  messageElement.classList.add(sender + '-message');
  messageElement.textContent = message;
  
  chatMessages.appendChild(messageElement);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add thinking indicator
function addThinkingIndicator() {
  const id = 'thinking-' + Date.now();
  const thinkingElement = document.createElement('div');
  thinkingElement.id = id;
  thinkingElement.classList.add('chat-message', 'assistant-message');
  thinkingElement.textContent = 'Thinking...';
  
  chatMessages.appendChild(thinkingElement);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  
  return id;
}

// Remove thinking indicator
function removeThinkingIndicator(id) {
  const thinkingElement = document.getElementById(id);
  if (thinkingElement) {
    thinkingElement.remove();
  }
}

// Event listeners for rename tab
renameBrowseBtn.addEventListener('click', async () => {
  const directoryPath = await ipcRenderer.invoke('select-directory');
  if (directoryPath) {
    renameDirectoryInput.value = directoryPath;
    loadFilesForRenaming(directoryPath);
  }
});

renameDirectoryInput.addEventListener('input', () => {
  if (renameDirectoryInput.value.trim()) {
    loadFilesForRenaming(renameDirectoryInput.value.trim());
  }
});

// Update generate names function
generateNamesBtn.addEventListener('click', async () => {
  if (!filesToRename.length) return;
  
  try {
    // Check rate limits if in online mode
    if (modeToggle.checked) {
      const canProceed = await checkRateLimits();
      if (!canProceed) return;
    }
    
    // Increment call counter
    await ipcRenderer.invoke('update-call-usage');
    
    generateNamesBtn.disabled = true;
    renameApplyBtn.disabled = true;
    showMessage('Generating new filenames...', 'info');
    
    const result = await ipcRenderer.invoke('generate-filenames', {
      files: filesToRename,
      online_mode: modeToggle.checked
    });
    
    if (result.success) {
      // Ensure generatedNames is initialized as an object
      generatedNames = result.generated_names || {};
      console.log('Successfully received generated names:', generatedNames);
      
      // Directly enable the rename button here
      const renameBtn = document.getElementById('renameApplyBtn');
      if (renameBtn && Object.keys(generatedNames).length > 0) {
        renameBtn.disabled = false;
        console.log('Directly enabled the rename button:', renameBtn);
      }
      
      updateRenamePreview();
      updateRenameButtons();
      
      showMessage('New filenames generated successfully!', 'success');
      
      // Force add click handler to ensure button works
      setTimeout(() => {
        const btn = document.getElementById('renameApplyBtn');
        if (btn) {
          btn.disabled = false;
          console.log('Force-enabled rename button after delay');
          btn.addEventListener('click', (e) => {
            console.log('CLICK FROM DELAYED HANDLER');
            performRename();
          });
        }
      }, 500);
    } else {
      showMessage(`Error: ${result.error}`, 'error');
    }
  } catch (error) {
    console.error('Error generating names:', error);
    showMessage(`Error: ${error.message}`, 'error');
  } finally {
    generateNamesBtn.disabled = false;
  }
});

// Add event listeners for select all/deselect all
document.getElementById('selectAllBtn').addEventListener('click', () => {
  selectedFiles = new Set(filesToRename.map(file => file.name));
  updateRenamePreview();
});

document.getElementById('deselectAllBtn').addEventListener('click', () => {
  selectedFiles.clear();
  updateRenamePreview();
});

function updateRenamePreview() {
  if (!filesToRename.length) {
    renamePreview.innerHTML = '<div class="rename-preview-item">No files to rename</div>';
    return;
  }

  renamePreview.innerHTML = '';
  filesToRename.forEach(file => {
    const item = document.createElement('div');
    item.className = 'rename-preview-item';
    
    // Original name
    const originalName = document.createElement('div');
    originalName.className = 'original';
    originalName.textContent = file.name;
    // Add tooltip data attribute for long filenames
    originalName.setAttribute('data-tooltip', file.name);
    
    // New name container
    const newName = document.createElement('div');
    newName.className = 'new';
    
    // Text display
    const newNameText = document.createElement('span');
    const displayName = generatedNames[file.name] || file.name;
    newNameText.textContent = displayName;
    // Add tooltip data attribute for long filenames
    newNameText.setAttribute('data-tooltip', displayName);
    
    // Input field (hidden by default)
    const newNameInput = document.createElement('input');
    newNameInput.type = 'text';
    newNameInput.value = generatedNames[file.name] || file.name;
    newNameInput.addEventListener('blur', () => {
      item.classList.remove('editing');
      if (newNameInput.value.trim() !== '') {
        generatedNames[file.name] = newNameInput.value;
        newNameText.textContent = newNameInput.value;
        // Update tooltip when the name changes
        newNameText.setAttribute('data-tooltip', newNameInput.value);
        updateRenameButtons();
      }
    });
    newNameInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        newNameInput.blur();
      }
    });
    
    newName.appendChild(newNameText);
    newName.appendChild(newNameInput);
    
    // File type badge
    const type = document.createElement('div');
    const typeBadge = document.createElement('span');
    typeBadge.className = 'type-badge';
    const fileExt = file.name.split('.').pop().toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(fileExt)) {
      typeBadge.classList.add('image');
      typeBadge.textContent = 'Image';
    } else if (fileExt === 'pdf') {
      typeBadge.classList.add('pdf');
      typeBadge.textContent = 'PDF';
    } else {
      typeBadge.textContent = fileExt.toUpperCase();
    }
    type.appendChild(typeBadge);
    
    // File size
    const size = document.createElement('div');
    size.className = 'size';
    size.textContent = formatFileSize(file.size);
    
    // Edit button
    const actions = document.createElement('div');
    const editBtn = document.createElement('button');
    editBtn.className = 'edit-btn';
    editBtn.innerHTML = '✏️';
    editBtn.title = 'Edit name';
    editBtn.addEventListener('click', () => {
      // Remove editing class from any other items
      document.querySelectorAll('.rename-preview-item').forEach(el => {
        if (el !== item) el.classList.remove('editing');
      });
      // Toggle editing for this item
      item.classList.add('editing');
      newNameInput.focus();
      newNameInput.select();
    });
    actions.appendChild(editBtn);
    
    // Add all elements to the item
    item.appendChild(originalName);
    item.appendChild(newName);
    item.appendChild(type);
    item.appendChild(size);
    item.appendChild(actions);
    
    renamePreview.appendChild(item);
  });
  
  updateRenameButtons();
}

// Add click event listener to handle clicking outside of editing items
document.addEventListener('click', (e) => {
  if (!e.target.closest('.rename-preview-item')) {
    document.querySelectorAll('.rename-preview-item').forEach(item => {
      item.classList.remove('editing');
    });
  }
});

function formatFileSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

function updateRenameButtons() {
  console.log('updateRenameButtons called');
  const hasChanges = generatedNames && Object.keys(generatedNames).length > 0;
  console.log('Has changes:', hasChanges, 'generatedNames:', generatedNames);
  
  // Access the buttons directly from the DOM again for safety
  const genNamesBtn = document.getElementById('generateNamesBtn');
  const renameBtn = document.getElementById('renameApplyBtn');
  
  console.log('Button references:', {
    genNamesBtn: genNamesBtn ? 'found' : 'not found',
    renameBtn: renameBtn ? 'found' : 'not found'
  });
  
  if (genNamesBtn) {
    genNamesBtn.disabled = !filesToRename.length;
    console.log('Set generateNamesBtn.disabled =', !filesToRename.length);
  }
  
  if (renameBtn) {
    renameBtn.disabled = !hasChanges;
    console.log('Set renameApplyBtn.disabled =', !hasChanges);
    
    // Add a direct click handler to ensure it works
    if (!renameBtn._hasClickListener) {
      renameBtn.addEventListener('click', function(e) {
        console.log('CLICK FROM updateRenameButtons');
        if (!renameBtn.disabled) {
          performRename();
        }
      });
      renameBtn._hasClickListener = true;
      console.log('Added click listener in updateRenameButtons');
    }
  }
}

// Add a console log to debug renameApplyBtn
console.log('Rename button element:', renameApplyBtn);

// Add a direct check for the button and add click event listener again
document.addEventListener('DOMContentLoaded', function() {
  console.log('DOMContentLoaded event fired');
  
  // Debug button elements
  const allButtons = document.querySelectorAll('button');
  console.log('Found buttons on page:', allButtons.length);
  allButtons.forEach(btn => {
    console.log('Button:', btn.id, btn.textContent);
  });
  
  // Check for renameApplyBtn specifically
  const btnCheck = document.getElementById('renameApplyBtn');
  console.log('renameApplyBtn element:', btnCheck);
  
  if (btnCheck) {
    console.log('Adding click listener to renameApplyBtn');
    btnCheck.addEventListener('click', function() {
      console.log('DIRECT CLICK HANDLER TRIGGERED');
      if (renameApplyBtn.disabled) {
        console.log('Button is disabled, not proceeding');
        return;
      }
      console.log('Proceeding with rename');
      
      // Simple immediate visual feedback
      showMessage('Processing rename...', 'info');
      
      // Call the actual rename function
      performRename();
    });
  } else {
    console.error('renameApplyBtn not found in the DOM!');
  }
});

// Function to update button state
function updateButtonState(button, state) {
  if (!button) return;
  
  // Reset all states
  button.classList.remove('loading', 'success');
  button.querySelectorAll('span').forEach(span => span.style.display = 'none');
  
  // Set the new state
  if (state === 'loading') {
    button.classList.add('loading');
    const loadingText = button.querySelector('.loading-text');
    if (loadingText) loadingText.style.display = 'inline';
  } else if (state === 'success') {
    button.classList.add('success');
    const successText = button.querySelector('.success-text');
    if (successText) successText.style.display = 'inline';
  } else {
    // Default state
    const defaultText = button.querySelector('.default-text');
    if (defaultText) defaultText.style.display = 'inline';
  }
}

// Extract the rename functionality to a separate function
async function performRename() {
  console.log('performRename function called');
  
  try {
    debugLog('Rename button clicked', {
      filesToRename,
      generatedNames
    });
    
    console.log('Current filesToRename:', filesToRename);
    console.log('Current generatedNames:', generatedNames);

    if (!filesToRename || filesToRename.length === 0) {
      console.error('No files to rename - filesToRename is empty or null');
      showMessage('No files to rename', 'error');
      return;
    }
    
    if (!generatedNames || Object.keys(generatedNames).length === 0) {
      console.error('No generated names available - generatedNames is empty or null');
      showMessage('No generated names available. Please generate names first.', 'error');
      return;
    }

    // Get direct reference to the button
    const renameBtn = document.getElementById('renameApplyBtn');
    
    // Show loading state
    updateButtonState(renameBtn, 'loading');
    
    showMessage('Renaming files...', 'info');
    // Show loader
    loader.style.display = 'flex';
    if (renameBtn) renameBtn.disabled = true;

    // Filter files that actually need renaming
    const filesToProcess = filesToRename
      .filter(file => {
        // Skip files without names
        if (!file || !file.name) {
          console.warn('Skipping file without name:', file);
          return false;
        }
        
        const newName = generatedNames[file.name];
        const needsRename = newName && newName !== file.name;
        debugLog('File rename check', {
          file: file.path,
          newName,
          needsRename
        });
        return needsRename;
      })
      .map(file => ({
        oldPath: file.path,
        newName: generatedNames[file.name]
      }));

    console.log('Files to process for renaming:', filesToProcess);

    if (filesToProcess.length === 0) {
      console.warn('No files need renaming - all names unchanged');
      showMessage('No files need renaming', 'info');
      loader.style.display = 'none';
      if (renameBtn) {
        renameBtn.disabled = false;
        updateButtonState(renameBtn, 'default');
      }
      return;
    }

    // Use direct file system rename instead of IPC call
    const results = [];
    const errors = [];

    for (const file of filesToProcess) {
      try {
        const directory = path.dirname(file.oldPath);
        const filename = path.basename(file.oldPath);
        const newPath = path.join(directory, file.newName);
        
        console.log(`Renaming: ${file.oldPath} -> ${newPath}`);
        
        // Check if destination already exists
        if (fs.existsSync(newPath)) {
          console.warn(`File already exists: ${newPath}`);
          // Add a counter to make the filename unique
          let counter = 1;
          let newNameWithCounter = file.newName;
          const ext = path.extname(file.newName);
          const baseName = path.basename(file.newName, ext);
          
          while (fs.existsSync(path.join(directory, newNameWithCounter))) {
            newNameWithCounter = `${baseName}_${counter}${ext}`;
            counter++;
          }
          
          const uniquePath = path.join(directory, newNameWithCounter);
          console.log(`Using unique name instead: ${uniquePath}`);
          
          // Rename the file
          fs.renameSync(file.oldPath, uniquePath);
          results.push({
            original: filename,
            new: newNameWithCounter,
            uniquePathUsed: true
          });
        } else {
          // Rename the file
          fs.renameSync(file.oldPath, newPath);
          results.push({
            original: filename,
            new: file.newName
          });
        }
      } catch (err) {
        console.error(`Error renaming ${file.oldPath}:`, err);
        errors.push({
          file: file.oldPath,
          error: err.message
        });
      }
    }

    // Display results
    if (errors.length === 0) {
      debugLog('Files renamed successfully', results);
      showMessage(`Successfully renamed ${results.length} files!`, 'success');
      
      // Set success state on button
      if (renameBtn) {
        updateButtonState(renameBtn, 'success');
        
        // Reset to default state after 2 seconds
        setTimeout(() => {
          updateButtonState(renameBtn, 'default');
        }, 2000);
      }
      
      // Clear the generated names since they've been applied
      generatedNames = {};
      
      // Reload the file list for the current directory
      if (results.length > 0 && filesToProcess.length > 0) {
        const dirPath = path.dirname(filesToProcess[0].oldPath);
        await loadFilesForRenaming(dirPath);
      }
    } else if (results.length > 0) {
      debugLog('Some files renamed with errors', { results, errors });
      showMessage(`Renamed ${results.length} files with ${errors.length} errors.`, 'warning');
      
      // Reset button state
      if (renameBtn) updateButtonState(renameBtn, 'default');
    } else {
      debugLog('Failed to rename files', errors);
      showMessage(`Failed to rename files: ${errors[0].error}`, 'error');
      
      // Reset button state
      if (renameBtn) updateButtonState(renameBtn, 'default');
    }
  } catch (error) {
    console.error('Error in rename operation:', error);
    debugLog('Error in rename operation', error);
    showMessage(`Failed to rename files: ${error.message}`, 'error');
    
    // Reset button state
    const renameBtn = document.getElementById('renameApplyBtn');
    if (renameBtn) updateButtonState(renameBtn, 'default');
  } finally {
    // Hide loader
    loader.style.display = 'none';
    
    // Re-enable button after a short delay
    setTimeout(() => {
      const renameBtn = document.getElementById('renameApplyBtn');
      if (renameBtn) renameBtn.disabled = false;
    }, 1000);
  }
}

async function loadFilesForRenaming(directoryPath) {
  try {
    if (!directoryPath) {
      showMessage('Please select a directory', 'error');
      return;
    }

    showMessage('Loading files...', 'info');
    const files = await ipcRenderer.invoke('get-files', directoryPath);
    
    if (!files || files.length === 0) {
      showMessage('No files found in the selected directory', 'info');
      filesToRename = [];
      generatedNames = {};
      renamePreview.innerHTML = '';
      generateNamesBtn.disabled = true;
      renameApplyBtn.disabled = true;
      return;
    }

    filesToRename = files;
    generatedNames = {};
    updateRenamePreview();
    generateNamesBtn.disabled = !files.length;
    renameApplyBtn.disabled = true;
    showMessage(`Loaded ${files.length} files`, 'success');
  } catch (error) {
    console.error('Error loading files:', error);
    showMessage(`Error loading files: ${error.message}`, 'error');
    filesToRename = [];
    generatedNames = {};
    renamePreview.innerHTML = '';
    generateNamesBtn.disabled = true;
    renameApplyBtn.disabled = true;
  }
}

// Initialize mode toggle state - add this at the bottom of the file and also 
// add it to a window.onload or DOMContentLoaded event
document.addEventListener('DOMContentLoaded', async function() {
  // Initialize mode toggle to match main process state
  const currentMode = await ipcRenderer.invoke('get-online-mode');
  console.log(`Initializing mode toggle to: ${currentMode ? 'ONLINE' : 'OFFLINE'}`);
  modeToggle.checked = currentMode;
});

// Add this at the end of the file to ensure it runs after everything else
setTimeout(() => {
  console.log('Delayed check for renameApplyBtn');
  const renameBtn = document.querySelector('button#renameApplyBtn');
  console.log('Found renameApplyBtn via querySelector:', renameBtn);
  
  if (renameBtn) {
    console.log('Adding direct click handler');
    // Remove any existing listeners to avoid duplicates
    renameBtn.replaceWith(renameBtn.cloneNode(true));
    
    // Get the fresh reference to the button after clone
    const freshRenameBtn = document.querySelector('button#renameApplyBtn');
    
    // Add direct event listener
    freshRenameBtn.addEventListener('click', (event) => {
      console.log('DIRECT CLICK ON RENAME BUTTON');
      event.preventDefault();
      event.stopPropagation();
      
      if (!freshRenameBtn.disabled) {
        showMessage('Initiating rename process...', 'info');
        performRename();
      } else {
        console.log('Button is disabled, not proceeding');
      }
    });
    
    // Force-enable the button if there are generated names
    if (generatedNames && Object.keys(generatedNames).length > 0) {
      freshRenameBtn.disabled = false;
      console.log('Force-enabled the rename button');
    }
  } else {
    console.error('Could not find renameApplyBtn even with querySelector!');
  }
}, 1000); // 1 second delay to ensure DOM is fully loaded

const TOKEN_LIMIT = 30000;
const CALL_LIMIT = 10;

// ============================================================
// Live Mode
// ============================================================

const liveDirectoryInput = document.getElementById('liveDirectoryPath');
const liveBrowseBtn = document.getElementById('liveBrowseBtn');
const liveToggleBtn = document.getElementById('liveToggleBtn');
const liveStatus = document.getElementById('liveStatus');
const liveSuggestions = document.getElementById('liveSuggestions');

let isLiveWatching = false;

// Browse for directory
liveBrowseBtn.addEventListener('click', async () => {
  const directoryPath = await ipcRenderer.invoke('select-directory');
  if (directoryPath) {
    liveDirectoryInput.value = directoryPath;
  }
});

// Toggle start/stop watching
liveToggleBtn.addEventListener('click', async () => {
  if (isLiveWatching) {
    // Stop watching
    try {
      await ipcRenderer.invoke('stop-live-watch');
      isLiveWatching = false;
      liveToggleBtn.textContent = 'Start Watching';
      liveStatus.textContent = 'Stopped';
      liveStatus.classList.remove('watching');
      showMessage('Live watcher stopped.', 'info');
    } catch (error) {
      showMessage(`Error stopping watcher: ${error.message}`, 'error');
    }
  } else {
    // Start watching
    const directory = liveDirectoryInput.value.trim();
    if (!directory) {
      showMessage('Please select a directory to watch.', 'error');
      return;
    }

    const isValid = await ipcRenderer.invoke('validate-directory', directory);
    if (!isValid) {
      showMessage('Please enter a valid directory path.', 'error');
      return;
    }

    try {
      const onlineMode = modeToggle.checked;
      await ipcRenderer.invoke('start-live-watch', {
        directory: directory,
        online_mode: onlineMode
      });
      isLiveWatching = true;
      liveToggleBtn.textContent = 'Stop Watching';
      liveStatus.textContent = 'Watching...';
      liveStatus.classList.add('watching');
      showMessage(`Now watching: ${directory}`, 'success');
    } catch (error) {
      showMessage(`Error starting watcher: ${error.message}`, 'error');
    }
  }
});

// Handle watcher stopped event (e.g. process crashed)
ipcRenderer.on('live-watcher-stopped', () => {
  if (isLiveWatching) {
    isLiveWatching = false;
    liveToggleBtn.textContent = 'Start Watching';
    liveStatus.textContent = 'Stopped';
    liveStatus.classList.remove('watching');
  }
});

// Handle incoming suggestions
ipcRenderer.on('live-suggestion', (event, suggestion) => {
  const card = document.createElement('div');
  card.className = 'suggestion-card';

  card.innerHTML = `
    <div class="suggestion-header">
      <span class="suggestion-filename">${escapeHtml(suggestion.filename)}</span>
      <span class="suggestion-category">${escapeHtml(suggestion.category)}</span>
    </div>
    <div class="suggestion-summary">${escapeHtml(suggestion.summary)}</div>
    <div class="suggestion-path">Move to: ${escapeHtml(suggestion.dst_path)}</div>
    <div class="suggestion-actions">
      <button class="accept-btn">Accept</button>
      <button class="ignore-btn">Ignore</button>
    </div>
  `;

  const acceptBtn = card.querySelector('.accept-btn');
  const ignoreBtn = card.querySelector('.ignore-btn');

  acceptBtn.addEventListener('click', async () => {
    try {
      acceptBtn.disabled = true;
      acceptBtn.textContent = 'Applying...';
      const fileStructure = {
        files: [
          {
            src_path: suggestion.src_path,
            dst_path: suggestion.dst_path
          }
        ]
      };
      await ipcRenderer.invoke('apply-changes', fileStructure);
      card.style.opacity = '0.5';
      acceptBtn.textContent = 'Applied';
      ignoreBtn.style.display = 'none';
      showMessage(`Moved ${suggestion.filename} to ${suggestion.category}/`, 'success');
    } catch (error) {
      acceptBtn.disabled = false;
      acceptBtn.textContent = 'Accept';
      showMessage(`Error moving file: ${error.message}`, 'error');
    }
  });

  ignoreBtn.addEventListener('click', () => {
    card.remove();
  });

  // Prepend so newest suggestions are at the top
  liveSuggestions.prepend(card);
});

// Helper to escape HTML to prevent injection
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}