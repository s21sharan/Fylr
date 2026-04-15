const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function getPythonPath() {
  // First, try the venv folder in the project directory
  const venvPath = path.join(__dirname, 'venv', 'bin', 'python');
  if (fs.existsSync(venvPath)) {
    console.log('[DEBUG] Using venv Python:', venvPath);
    return venvPath;
  }

  // Check for environment variable
  if (process.env.VIRTUAL_ENV) {
    const pythonBin = process.platform === 'win32' ? 'python.exe' : 'python';
    const pythonPath = path.join(process.env.VIRTUAL_ENV, 'bin', pythonBin);

    if (fs.existsSync(pythonPath)) {
      console.log('[DEBUG] Using VIRTUAL_ENV Python:', pythonPath);
      return pythonPath;
    }
  }

  // Try to find using commands
  try {
    if (process.platform === 'win32') {
      return execSync('where python').toString().trim().split('\n')[0];
    } else {
      // Try python3 first, then python
      try {
        const python3Path = execSync('which python3').toString().trim();
        if (python3Path) {
          console.log('[DEBUG] Using system python3:', python3Path);
          return python3Path;
        }
      } catch (e) {
        // Try python
        const pythonPath = execSync('which python').toString().trim();
        console.log('[DEBUG] Using system python:', pythonPath);
        return pythonPath;
      }
    }
  } catch (e) {
    // Fall back to python3
    console.log('[DEBUG] Falling back to python3');
    return 'python3';
  }
}

module.exports = { getPythonPath }; 