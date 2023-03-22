// src/components/CodeBlockWithLabel.jsx
import React from 'react';
import CodeBlock from '@theme/CodeBlock';

const CustomLabels = ({ code, language, labelId, labelContent }) => {
  const labelElement = `<label id="${labelId}">${labelContent}</label>`;
  const codeWithLabel = code.replace('{label}', labelElement);

  return <CodeBlock className={language} children={codeWithLabel} />;
};

export default CustomLabels;
