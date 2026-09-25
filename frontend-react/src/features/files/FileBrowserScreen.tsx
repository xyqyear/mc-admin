import React from 'react'
import { Folder, Search } from 'lucide-react'
import { useParams } from 'react-router'

import { Card, CardContent } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'

import PageHeader from '@/shared/layout/PageHeader'
import ArchiveSelectionDialog from '@/features/archives/ui/ArchiveSelectionDialog'
import PopulateProgressDialog from '@/features/archives/ui/PopulateProgressDialog'
import DragDropOverlay from '@/shared/components/DragDropOverlay'
import {
  MultiFileUploadDialog,
  CreateDialog,
  RenameDialog,
  FileEditDialog,
  FileDiffDialog,
  CompressionConfirmDialog,
  CompressionResultDialog,
  FileDeepSearchDialog
} from '@/features/files/components/dialogs/index'
import { useFileBrowser } from '@/features/files/useFileBrowser'
import FileTable from '@/features/files/components/FileTable'
import FileToolbar from '@/features/files/components/FileToolbar'
import FileBreadcrumb from '@/features/files/components/FileBreadcrumb'
import FileSearchBox from '@/features/files/components/FileSearchBox'

const ServerFiles: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const {
    filesError,
    fileData,
    isDragging,
    isScanning,
    hasServerInfo,
    serverInfo,
    currentPath,
    selectedFiles,
    isFetchingFiles,
    createArchiveMutation,
    populateServerMutation,
    bulkDeleteMutation,
    restoreOwnershipMutation,
    ownershipTask,
    handleNavigateToParent,
    handleRefresh,
    setIsMultiFileUploadDialogOpen,
    setIsCreateDialogOpen,
    handleBulkDelete,
    handleCompressServer,
    handleReplaceServerFiles,
    handleRestoreOwnership,
    refetch,
    handleNavigateToPath,
    searchBoxRef,
    inputSearchTerm,
    useRegex,
    handleSearchChange,
    handleRegexChange,
    handleSearchClear,
    handleSearch,
    setIsDeepSearchDialogOpen,
    filteredFileData,
    isLoadingFiles,
    setSelectedFiles,
    currentPage,
    pageSize,
    setCurrentPage,
    setPageSize,
    handleFileEdit,
    handleFileDelete,
    handleFileDownload,
    handleFileRename,
    handleFolderOpen,
    handleCompress,
    isMultiFileUploadDialogOpen,
    setSelectedUploadFiles,
    handleMultiFileUploadComplete,
    selectedUploadFiles,
    isCreateDialogOpen,
    handleCreateFile,
    createFileMutation,
    isRenameDialogOpen,
    setIsRenameDialogOpen,
    setRenamingFile,
    handleRenameSubmit,
    renamingFile,
    renameFileMutation,
    isEditDialogOpen,
    closeEditor,
    handleFileSave,
    handleShowDiff,
    editingFile,
    fileContent,
    setFileContent,
    originalFileContent,
    isLoadingContent,
    editorDraft,
    contentError,
    refetchContent,
    updateFileMutation,
    getCurrentFileLanguageConfig,
    isDiffDialogOpen,
    setIsDiffDialogOpen,
    isArchiveDialogOpen,
    setIsArchiveDialogOpen,
    handleArchiveSelect,
    isPopulateProgressDialogOpen,
    populateTaskId,
    handlePopulateClose,
    handlePopulateComplete,
    isCompressionConfirmDialogOpen,
    setIsCompressionConfirmDialogOpen,
    setCompressionFile,
    setCompressionTaskId,
    handleCompressionConfirm,
    compressionTask,
    compressionFile,
    compressionType,
    isCompressionResultDialogOpen,
    setIsCompressionResultDialogOpen,
    setCompressionResult,
    compressionResult,
    handleDownloadCompressed,
    isDeepSearchDialogOpen,
    handleDeepSearchNavigate,
    confirmDialog
  } = useFileBrowser(id)

  if (filesError && !fileData) {
    return <Alert variant="destructive"><AlertTitle>加载文件列表失败</AlertTitle><AlertDescription>{filesError.message}<Button variant="outline" onClick={handleRefresh} disabled={isFetchingFiles}>重试</Button></AlertDescription></Alert>
  }

  return (
    <div className="space-y-4">
      <DragDropOverlay
        isDragging={isDragging}
        isScanning={isScanning}
        allowDirectories={true}
        pageType="serverFiles"
      />

      <PageHeader
        title="文件"
        icon={<Folder className="h-5 w-5" />}
        serverTag={hasServerInfo ? serverInfo?.name : undefined}
        actions={
          <FileToolbar
            currentPath={currentPath}
            selectedFiles={selectedFiles}
            serverId={id || ''}
            isLoadingFiles={isFetchingFiles}
            createArchiveMutation={createArchiveMutation}
            populateServerMutation={populateServerMutation}
            bulkDeleteMutation={bulkDeleteMutation}
            restoreOwnershipMutation={{
              isPending:
                restoreOwnershipMutation.isPending ||
                ownershipTask?.status === 'pending' ||
                ownershipTask?.status === 'running',
            }}
            onNavigateToParent={handleNavigateToParent}
            onRefresh={handleRefresh}
            onUpload={() => setIsMultiFileUploadDialogOpen(true)}
            onCreateFile={() => setIsCreateDialogOpen(true)}
            onBulkDelete={handleBulkDelete}
            onCompressServer={handleCompressServer}
            onReplaceServerFiles={handleReplaceServerFiles}
            onRestoreOwnership={handleRestoreOwnership}
            onRefreshSnapshot={refetch}
          />
        }
      />

      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <FileBreadcrumb
              currentPath={currentPath}
              onNavigateToPath={handleNavigateToPath}
            />
            <div className="flex items-center gap-2">
              <div className="shrink-0 min-w-75 max-w-md">
                <FileSearchBox
                  ref={searchBoxRef}
                  searchTerm={inputSearchTerm}
                  useRegex={useRegex}
                  onSearchChange={handleSearchChange}
                  onRegexChange={handleRegexChange}
                  onClear={handleSearchClear}
                  onSearch={handleSearch}
                  placeholder="按回车键搜索当前文件夹..."
                />
              </div>
              <Button
                variant="outline"
                onClick={() => setIsDeepSearchDialogOpen(true)}
              >
                <Search className="mr-2 h-4 w-4" />
                高级搜索
              </Button>
            </div>
          </div>

          <FileTable
            fileData={filteredFileData}
            isLoadingFiles={isLoadingFiles}
            selectedFiles={selectedFiles}
            setSelectedFiles={setSelectedFiles}
            currentPage={currentPage}
            pageSize={pageSize}
            setCurrentPage={setCurrentPage}
            setPageSize={setPageSize}
            serverId={id || ''}
            onFileEdit={handleFileEdit}
            onFileDelete={handleFileDelete}
            onFileDownload={handleFileDownload}
            onFileRename={handleFileRename}
            onFolderOpen={handleFolderOpen}
            onFileCompress={handleCompress}
            createArchiveMutation={createArchiveMutation}
          />
        </CardContent>
      </Card>

      <MultiFileUploadDialog
        open={isMultiFileUploadDialogOpen}
        onCancel={() => {
          setIsMultiFileUploadDialogOpen(false)
          setSelectedUploadFiles([])
        }}
        onComplete={handleMultiFileUploadComplete}
        serverId={id || ''}
        basePath={currentPath}
        initialFiles={selectedUploadFiles}
      />

      <CreateDialog
        open={isCreateDialogOpen}
        onCancel={() => setIsCreateDialogOpen(false)}
        onSubmit={handleCreateFile}
        confirmLoading={createFileMutation.isPending}
      />

      <RenameDialog
        open={isRenameDialogOpen}
        onCancel={() => {
          setIsRenameDialogOpen(false)
          setRenamingFile(null)
        }}
        onSubmit={handleRenameSubmit}
        initialName={renamingFile?.name}
        confirmLoading={renameFileMutation.isPending}
      />

      <FileEditDialog
        open={isEditDialogOpen}
        onCancel={closeEditor}
        onSave={handleFileSave}
        onShowDiff={handleShowDiff}
        editingFile={editingFile}
        fileContent={fileContent}
        setFileContent={setFileContent}
        originalFileContent={originalFileContent}
        isLoadingContent={isLoadingContent}
        contentReady={editorDraft.ready}
        contentError={contentError?.message}
        onRetry={() => { void refetchContent() }}
        confirmLoading={updateFileMutation.isPending}
        serverId={id || ''}
        getCurrentFileLanguageConfig={getCurrentFileLanguageConfig}
      />

      <FileDiffDialog
        open={isDiffDialogOpen}
        onCancel={() => setIsDiffDialogOpen(false)}
        originalFileContent={originalFileContent}
        fileContent={fileContent}
        serverId={id || ''}
        getCurrentFileLanguageConfig={getCurrentFileLanguageConfig}
      />

      <Alert>
        <AlertTitle>文件管理说明</AlertTitle>
        <AlertDescription>
          您可以浏览、编辑和管理服务器文件。点击文件夹名称或文件夹图标可以进入目录。配置文件可以直接编辑，其他文件可以下载查看。上传的文件将保存到当前目录中。
        </AlertDescription>
      </Alert>

      <ArchiveSelectionDialog
        open={isArchiveDialogOpen}
        onCancel={() => setIsArchiveDialogOpen(false)}
        onSelect={handleArchiveSelect}
        title="选择压缩包文件"
        description="选择要用于替换服务器文件的压缩包文件"
        selectButtonText="替换服务器文件"
        selectButtonType="danger"
      />

      <PopulateProgressDialog
        open={isPopulateProgressDialogOpen}
        taskId={populateTaskId}
        serverId={id || ''}
        onClose={handlePopulateClose}
        onComplete={handlePopulateComplete}
      />

      <CompressionConfirmDialog
        open={isCompressionConfirmDialogOpen}
        onCancel={() => {
          setIsCompressionConfirmDialogOpen(false)
          setCompressionFile(null)
          setCompressionTaskId(null)
        }}
        onOk={handleCompressionConfirm}
        confirmLoading={createArchiveMutation.isPending}
        task={compressionTask}
        selectedFile={compressionFile}
        currentPath={currentPath}
        compressionType={compressionType}
        serverName={hasServerInfo ? serverInfo?.name : ''}
      />

      <CompressionResultDialog
        open={isCompressionResultDialogOpen}
        onCancel={() => {
          setIsCompressionResultDialogOpen(false)
          setCompressionResult(null)
        }}
        archiveFilename={compressionResult?.filename || ''}
        message={compressionResult?.message || ''}
        onDownload={handleDownloadCompressed}
        downloadLoading={false}
      />

      <FileDeepSearchDialog
        open={isDeepSearchDialogOpen}
        onCancel={() => setIsDeepSearchDialogOpen(false)}
        serverId={id || ''}
        currentPath={currentPath}
        onNavigate={handleDeepSearchNavigate}
      />

      {confirmDialog}
    </div>
  )
}

export default ServerFiles
