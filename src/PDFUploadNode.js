import React, { useState } from 'react';
import { Handle } from '@xyflow/react';

const PDFUploadNode = ({ data = {} }) => {  // Default to empty object
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);

  const handleFileChange = (e) => {
    setFiles(Array.from(e.target.files));
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      alert('Please select at least one PDF file');
      return;
    }
    setUploading(true);
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    try {
      const response = await fetch('http://localhost:8000/upload_pdfs', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || 'Upload failed');
      }
      alert(result.message);
      console.log('Upload successful:', result.message);
      if (data.onUploadSuccess && result.session_id) {  // Remove optional chaining, check directly
        data.onUploadSuccess(result.session_id);
      }
      setFiles([]);
    } catch (error) {
      console.error('Upload error:', error.message);
      alert(`Failed to upload PDFs: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ padding: 10, background: '#fff', border: '1px solid #ddd' }}>
      <Handle type="target" position="left" />
      <Handle type="source" position="right" />
      <h4>PDF Upload</h4>
      <input
        type="file"
        multiple
        accept=".pdf"
        onChange={handleFileChange}
        disabled={uploading}
      />
      <button onClick={handleUpload} disabled={uploading}>
        {uploading ? 'Uploading...' : 'Upload'}
      </button>
    </div>
  );
};

export default PDFUploadNode;