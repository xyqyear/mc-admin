import React from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

interface SortableVariableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  "data-row-key"?: string;
}

const SortableVariableRow: React.FC<SortableVariableRowProps> = (props) => {
  const id = props["data-row-key"] ?? "";
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style: React.CSSProperties = {
    ...props.style,
    transform: CSS.Translate.toString(transform),
    transition,
    ...(isDragging ? { position: "relative", zIndex: 9999, opacity: 0.8 } : {}),
  };

  return (
    <tr
      {...props}
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
    />
  );
};

export default SortableVariableRow;
