package com.academy.message.model;

public class MessagePreview {
    private final ImportRow row;
    private String content;
    private boolean selectedToSend;
    private String status;

    public MessagePreview(ImportRow row, String content) {
        this.row = row;
        this.content = content;
        this.selectedToSend = false;
        this.status = "READY";
    }

    public ImportRow getRow() {
        return row;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public boolean isSelectedToSend() {
        return selectedToSend;
    }

    public void setSelectedToSend(boolean selectedToSend) {
        this.selectedToSend = selectedToSend;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
