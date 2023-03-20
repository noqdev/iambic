// src/components/CodeBlockWithLabel.jsx
import React, { useEffect, useRef } from 'react';
import CodeBlock from '@theme/CodeBlock';

const CodeBlockWithLabel = ({ code, language, labelId, labelContent }) => {
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (wrapperRef.current) {
      const labelElement = document.createElement('label');
      labelElement.id = labelId;
      labelElement.innerHTML = labelContent;

      const codeElement = wrapperRef.current.querySelector('code');
      codeElement.innerHTML = codeElement.innerHTML.replace('{label}', '');
      codeElement.insertBefore(labelElement, codeElement.firstChild);
    }
  }, [wrapperRef, labelId, labelContent]);

  return (
    <div ref={wrapperRef}>
      <CodeBlock className={language} children={code.replace('{label}', '')} />
    </div>
  );
};

export default CodeBlockWithLabel;
