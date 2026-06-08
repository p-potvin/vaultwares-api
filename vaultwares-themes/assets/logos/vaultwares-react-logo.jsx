import * as React from "react";
const SVGComponent = (props) => (
  <svg
    width={200}
    height={200}
    viewBox="0 0 24 24"
    fill="none"
    stroke="#4ecc21"
    strokeWidth={1.75}
    {...props}
  >
    <path d="M12 1v6m0 0 4-4m-4 4L8 3m12 9h-6m0 0 4 4m-4-4-4 4m2 4v-6m0 0-4 4m4-4 4 4" />
  </svg>
);
export default SVGComponent;
