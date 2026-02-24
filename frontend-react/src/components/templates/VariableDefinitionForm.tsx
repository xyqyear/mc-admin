import React, { useState, useCallback, useRef, useMemo } from "react";
import { Table, Button, Input, Tag, Popconfirm, Empty, Space } from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  HolderOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import SortableVariableRow from "./SortableVariableRow";
import VariableEditModal from "./VariableEditModal";
import type { VariableFormData } from "./variableSchemas";

// Re-export for backwards compatibility
export type { VariableFormData } from "./variableSchemas";

interface VariableDefinitionFormProps {
  value: VariableFormData[];
  onChange: (variables: VariableFormData[]) => void;
  disabled?: boolean;
  title?: string;
}

const TYPE_LABELS: Record<VariableFormData["type"], { label: string; color: string }> = {
  string: { label: "字符串", color: "blue" },
  int: { label: "整数", color: "green" },
  float: { label: "浮点数", color: "cyan" },
  enum: { label: "枚举", color: "orange" },
  bool: { label: "布尔值", color: "purple" },
};

interface KeyedVariable extends VariableFormData {
  _key: string;
}

const VariableDefinitionForm: React.FC<VariableDefinitionFormProps> = ({
  value,
  onChange,
  disabled = false,
  title,
}) => {
  const [searchText, setSearchText] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"add" | "edit">("add");
  const [editingIndex, setEditingIndex] = useState<number>(-1);
  const [editingData, setEditingData] = useState<Partial<VariableFormData> | undefined>();

  // Stable key counter for dnd-kit
  const keyCounter = useRef(0);
  const keyMapRef = useRef(new WeakMap<VariableFormData, string>());

  const getKey = useCallback((item: VariableFormData): string => {
    let key = keyMapRef.current.get(item);
    if (!key) {
      key = `var-${keyCounter.current++}`;
      keyMapRef.current.set(item, key);
    }
    return key;
  }, []);

  // Keyed items for table + dnd
  const keyedItems: KeyedVariable[] = useMemo(
    () => value.map((v) => ({ ...v, _key: getKey(v) })),
    [value, getKey]
  );

  const isSearching = searchText.trim().length > 0;

  const filteredItems = useMemo(() => {
    if (!isSearching) return keyedItems;
    const lower = searchText.toLowerCase();
    return keyedItems.filter(
      (v) =>
        v.name.toLowerCase().includes(lower) ||
        (v.display_name ?? "").toLowerCase().includes(lower)
    );
  }, [keyedItems, searchText, isSearching]);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor)
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      const oldIndex = keyedItems.findIndex((v) => v._key === active.id);
      const newIndex = keyedItems.findIndex((v) => v._key === over.id);
      if (oldIndex === -1 || newIndex === -1) return;
      const reordered = arrayMove([...value], oldIndex, newIndex);
      onChange(reordered);
    },
    [keyedItems, value, onChange]
  );

  // Modal handlers
  const openAddModal = useCallback(() => {
    setModalMode("add");
    setEditingIndex(-1);
    setEditingData(undefined);
    setModalOpen(true);
  }, []);

  const openEditModal = useCallback(
    (record: KeyedVariable) => {
      const idx = keyedItems.findIndex((v) => v._key === record._key);
      if (idx === -1) return;
      // Deep copy without _key
      const { _key: _unused, ...data } = record;
      void _unused;
      setModalMode("edit");
      setEditingIndex(idx);
      setEditingData(structuredClone(data));
      setModalOpen(true);
    },
    [keyedItems]
  );

  const handleModalOk = useCallback(
    (data: VariableFormData) => {
      const next = [...value];
      if (modalMode === "add") {
        next.push(data);
      } else if (editingIndex >= 0) {
        next[editingIndex] = data;
      }
      onChange(next);
      setModalOpen(false);
    },
    [value, onChange, modalMode, editingIndex]
  );

  const handleDelete = useCallback(
    (record: KeyedVariable) => {
      const idx = keyedItems.findIndex((v) => v._key === record._key);
      if (idx === -1) return;
      const next = [...value];
      next.splice(idx, 1);
      onChange(next);
    },
    [keyedItems, value, onChange]
  );

  const formatDefault = (val: unknown): string => {
    if (val === undefined || val === null) return "-";
    if (typeof val === "boolean") return val ? "true" : "false";
    return String(val);
  };

  const columns: ColumnsType<KeyedVariable> = [
    ...(disabled || isSearching
      ? []
      : [
          {
            title: "",
            dataIndex: "_drag",
            width: 40,
            render: () => (
              <HolderOutlined style={{ cursor: "grab", color: "#999" }} />
            ),
          } as const,
        ]),
    {
      title: "变量名",
      dataIndex: "name",
      render: (name: string) => (
        <code style={{ fontSize: 13 }}>{name || <span style={{ color: "#ccc" }}>-</span>}</code>
      ),
    },
    {
      title: "显示名称",
      dataIndex: "display_name",
      render: (v: string) => v || "-",
    },
    {
      title: "类型",
      dataIndex: "type",
      width: 90,
      render: (type: VariableFormData["type"]) => {
        const info = TYPE_LABELS[type];
        return info ? <Tag color={info.color}>{info.label}</Tag> : type;
      },
    },
    {
      title: "默认值",
      dataIndex: "default",
      ellipsis: true,
      render: (_: unknown, record: KeyedVariable) => formatDefault(record.default),
    },
    ...(disabled
      ? []
      : [
          {
            title: "操作",
            width: 80,
            render: (_: unknown, record: KeyedVariable) => (
              <Space size="small">
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openEditModal(record)}
                />
                <Popconfirm
                  title="确定删除该变量？"
                  onConfirm={() => handleDelete(record)}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          } as const,
        ]),
  ];

  const tableBody = {
    body: {
      row: isSearching || disabled ? undefined : SortableVariableRow,
    },
  };

  const sortableIds = keyedItems.map((v) => v._key);

  const emptyContent = (
    <Empty description="暂无变量">
      {!disabled && (
        <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
          添加变量
        </Button>
      )}
    </Empty>
  );

  return (
    <div>
      {title && (
        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 12 }}>{title}</div>
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          gap: 12,
        }}
      >
        <Input.Search
          placeholder="搜索变量名或显示名称"
          allowClear
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ maxWidth: 300 }}
        />
        {!disabled && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
            添加变量
          </Button>
        )}
      </div>

      {value.length === 0 ? (
        emptyContent
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={sortableIds}
            strategy={verticalListSortingStrategy}
          >
            <Table<KeyedVariable>
              rowKey="_key"
              columns={columns}
              dataSource={filteredItems}
              components={isSearching || disabled ? undefined : tableBody}
              pagination={false}
              size="small"
              locale={{ emptyText: "无匹配变量" }}
            />
          </SortableContext>
        </DndContext>
      )}

      <VariableEditModal
        open={modalOpen}
        mode={modalMode}
        initialData={editingData}
        onOk={handleModalOk}
        onCancel={() => setModalOpen(false)}
      />
    </div>
  );
};

export default VariableDefinitionForm;
