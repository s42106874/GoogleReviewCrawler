# Google Maps 評論爬蟲

## 功能
- 輸入地區與店家類型，自動搜尋 Google Maps 店家。
- 爬取在地嚮導評論（名稱、日期、內容、星級）。
- GUI 介面顯示進度與日誌，支援中止並儲存。
- 輸出 CSV 檔案。

## 技術
- Python
- Selenium（網頁爬取）
- BeautifulSoup（HTML 解析）
- tkinter（GUI）
- pandas（資料處理）
- ThreadPoolExecutor（多執行緒）

## 使用方法
1. 安裝依賴：
   ```bash
   pip install -r requirements.txt

2. 執行程式: 
    python google_review_crawler.py

3. 在GUI輸入:

    地區（如「台南市中西區」）
    類型（如「咖啡店」）
    目標評論數（0 表示全部）
    選擇儲存路徑

4. 點擊「執行」，結果存為 CSV。

注意事項
需安裝 Chrome 瀏覽器。
可能因 Google 反爬機制需調整等待時間。

