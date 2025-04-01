import React, { useState, useCallback } from 'react';
import { ReactFlow, addEdge, Background, Controls, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import PDFUploadNode from './PDFUploadNode';
import VectorDBNode from './VectorDBNode';
import LLMNode from './LLMNode';
import Chatbot from './Chatbot';

const nodeTypes = {
  pdfUpload: PDFUploadNode,
  vectorDB: VectorDBNode,
  llm: LLMNode,
};

const initialNodes = [
  { id: 'pdf', type: 'pdfUpload', position: { x: 100, y: 100 }, data: {} },  // Start with empty data
  { id: 'vectorDB', type: 'vectorDB', position: { x: 300, y: 100 }, data: {} },
  { id: 'llm', type: 'llm', position: { x: 500, y: 100 }, data: {} },
];

const App = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [useLLMState, setUseLLMState] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  const handleUploadSuccess = useCallback((newSessionId) => {
    setSessionId(newSessionId);
  }, []);

  // Ensure the pdf node always has the onUploadSuccess callback
  const updatedNodes = nodes.map(node =>
    node.id === 'pdf' ? { ...node, data: { ...node.data, onUploadSuccess: handleUploadSuccess } } : node
  );

  const onConnect = useCallback(async (params) => {
    setEdges((eds) => addEdge(params, eds));
    if ((params.source === 'pdf' && params.target === 'vectorDB') || (params.source === 'vectorDB' && params.target === 'pdf')) {
      setIsProcessing(true);
      try {
        const response = await fetch('http://localhost:8000/process_pdfs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ session_id: sessionId }),
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to create embeddings');
        }
        const result = await response.json();
        console.log(result.message);
        alert(result.message);
        setSessionId(result.session_id || sessionId);
      } catch (error) {
        console.error('Error creating embeddings:', error.message);
        alert(`Error: ${error.message}`);
      } finally {
        setIsProcessing(false);
      }
    } else if ((params.source === 'vectorDB' && params.target === 'llm') || (params.source === 'llm' && params.target === 'vectorDB')) {
      console.log('Connected Vector Database to OpenAI LLM');
      setUseLLMState(true);
    }
  }, [setEdges, sessionId]);

  const onEdgesChangeHandler = useCallback((changes) => {
    onEdgesChange(changes);
    const newEdges = changes.reduce((acc, change) => {
      if (change.type === 'remove') {
        return acc.filter((edge) => edge.id !== change.id);
      }
      return acc;
    }, edges);
    const hasLLMConnection = newEdges.some(
      (edge) =>
        (edge.source === 'vectorDB' && edge.target === 'llm') ||
        (edge.source === 'llm' && edge.target === 'vectorDB')
    );
    setUseLLMState(hasLLMConnection);
  }, [edges, onEdgesChange]);

  const useVectorDB = edges.some(
    (edge) =>
      (edge.source === 'pdf' && edge.target === 'vectorDB') ||
      (edge.source === 'vectorDB' && edge.target === 'pdf')
  );
  const useLLM = useLLMState;

  return (
    <div style={{ height: '100vh', position: 'relative' }}>
      {isProcessing && (
        <div style={{ position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)', background: '#fff', padding: 10, border: '1px solid #ccc' }}>
          Processing embeddings...
        </div>
      )}
      <ReactFlow
        nodes={updatedNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChangeHandler}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
      <Chatbot useVectorDB={useVectorDB} useLLM={useLLM} sessionId={sessionId} />
    </div>
  );
};

export default App;