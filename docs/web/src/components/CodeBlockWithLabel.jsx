import React, { useEffect, useRef } from 'react';
import CodeBlock from '@theme/CodeBlock';

const CodeBlockWithLabel = ({ code, language, labels }) => {
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (wrapperRef.current) {
      labels.forEach(({ id, content }) => {
        const labelElement = document.createElement('label');
        labelElement.id = id;
        labelElement.innerHTML = content;

        const codeElement = wrapperRef.current.querySelector('code');
        codeElement.innerHTML = codeElement.innerHTML.replace(`{${id}}`, '');
        codeElement.insertBefore(labelElement, codeElement.firstChild);
      });
    }
  }, [wrapperRef, code, labels]);

  return (
    <div ref={wrapperRef}>
      <CodeBlock className={language} children={code} />
    </div>
  );
};

export default CodeBlockWithLabel;
