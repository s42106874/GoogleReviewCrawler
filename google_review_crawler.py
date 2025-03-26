import random
import pandas as pd
import time
from bs4 import BeautifulSoup
import csv
import re
import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, filename='crawler.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

# 全局變數
stop_flag = False
all_data = []  # 儲存所有爬取的評論

def is_local_guide_html(review_soup):
    try:
        subtitle = review_soup.find(class_="RfnDt")
        return subtitle and "在地嚮導" in subtitle.text
    except Exception:
        return False

def click_show_more_buttons(driver):
    global stop_flag
    try:
        show_more_buttons = WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "w8nwRe"))
        )
        for button in show_more_buttons:
            if stop_flag:
                return False
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(0.1)  # 減少等待時間
            button.click()
            time.sleep(0.3)  # 減少等待時間
        logging.info("已處理所有『顯示更多』按鈕")
        return True
    except Exception:
        return False

def click_load_more_button(driver, text_widget, place_name):
    try:
        load_more_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '更多評論') or contains(text(), 'Load More')]"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", load_more_button)
        driver.execute_script("arguments[0].click();", load_more_button)
        text_widget.insert(tk.END, f"{place_name}: 已點擊「載入更多」按鈕\n")
        text_widget.see(tk.END)
        time.sleep(random.uniform(0.5, 1))  # 縮短隨機等待區間
        return True
    except (TimeoutException, NoSuchElementException):
        return False

def scroll_reviews(driver, place_name, target_reviews, text_widget):
    global stop_flag
    try:
        review_container = driver.find_element(By.CLASS_NAME, "m6QErb")
        prev_review_count = 0
        no_new_content_count = 0
        max_no_new_content = 2
        collected_reviews = 0

        # 初始排序：等待時間縮短
        try:
            sort_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '排序') or contains(@aria-label, 'Sort')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", sort_button)
            driver.execute_script("arguments[0].click();", sort_button)
            time.sleep(random.uniform(0.5, 1))
            newest_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), '最新') or contains(text(), 'Newest')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", newest_option)
            driver.execute_script("arguments[0].click();", newest_option)
            text_widget.insert(tk.END, f"{place_name}: 已點擊「最新」排序選項\n")
            text_widget.see(tk.END)
            time.sleep(1)  # 減少等待時間
        except Exception as e:
            text_widget.insert(tk.END, f"{place_name}: 排序選項點擊失敗 ({str(e)})，繼續滾動\n")
            text_widget.see(tk.END)

        while no_new_content_count < max_no_new_content:
            if stop_flag:
                text_widget.insert(tk.END, f"{place_name}: 停止滾動，因收到中止指令\n")
                text_widget.see(tk.END)
                return driver.page_source

            # 處理「顯示更多」和「載入更多」按鈕
            clicked = click_show_more_buttons(driver) or click_load_more_button(driver, text_widget, place_name)
            if clicked:
                time.sleep(random.uniform(0.2, 0.5))
            
            # 滾動到底部
            container_height = driver.execute_script("return arguments[0].scrollHeight", review_container)
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", review_container)
            
            # 確認觸底
            current_position = driver.execute_script("return arguments[0].scrollTop + arguments[0].offsetHeight", review_container)
            if current_position < container_height - 10:
                text_widget.insert(tk.END, f"{place_name}: 未完全觸底，重試滾動...\n")
                text_widget.see(tk.END)
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", review_container)
                time.sleep(random.uniform(0.2, 0.5))
            
            # 等待新評論
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: len(d.find_elements(By.CLASS_NAME, "jftiEf")) > prev_review_count
                )
                no_new_content_count = 0
            except TimeoutException:
                no_new_content_count += 1
                text_widget.insert(tk.END, f"{place_name}: 連續無新內容 {no_new_content_count}/{max_no_new_content}，再次嘗試...\n")
                text_widget.see(tk.END)
                time.sleep(random.uniform(1.0, 2.0))
                # 中途刷新頁面
                if no_new_content_count == 5:
                    text_widget.insert(tk.END, f"{place_name}: 評論載入停滯，嘗試刷新頁面...\n")
                    text_widget.see(tk.END)
                    driver.refresh()
                    time.sleep(3)
                    review_container = driver.find_element(By.CLASS_NAME, "m6QErb")
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", review_container)
            
            current_reviews = driver.find_elements(By.CLASS_NAME, "jftiEf")
            current_review_count = len(current_reviews)

            local_guides = [r for r in current_reviews if is_local_guide_html(BeautifulSoup(r.get_attribute('outerHTML'), "lxml"))]
            collected_reviews = len(local_guides)

            if current_review_count > prev_review_count:
                text_widget.insert(tk.END, f"{place_name}: 載入新評論，總數: {current_review_count}, 已蒐集在地嚮導評論: {collected_reviews}\n")
                text_widget.see(tk.END)
                prev_review_count = current_review_count
                no_new_content_count = 0
                if target_reviews > 0 and collected_reviews >= target_reviews:
                    text_widget.insert(tk.END, f"{place_name}: 已達目標評論數 {target_reviews}，停止滾動\n")
                    text_widget.see(tk.END)
                    return driver.page_source
            else:
                text_widget.insert(tk.END, f"{place_name}: 未載入新評論，繼續嘗試...\n")
                text_widget.see(tk.END)

        text_widget.insert(tk.END, f"{place_name}: 已停止滾動，最終評論數: {prev_review_count}, 總共蒐集在地嚮導評論: {collected_reviews}\n")
        text_widget.see(tk.END)
        return driver.page_source
    except Exception as e:
        text_widget.insert(tk.END, f"{place_name}: 滾動評論時發生錯誤: {str(e)}\n")
        text_widget.see(tk.END)
        logging.error(f"{place_name}: 滾動評論失敗: {str(e)}")
        return driver.page_source

def get_store_name_and_address(store_url):
    global stop_flag
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--enable-unsafe-swiftshader")
    options.add_argument("--disable-webgl")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.142 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        if stop_flag:
            return "未知店家名稱", "未知地址"
        driver.get(store_url)
        WebDriverWait(driver, 15).until(
            lambda driver: driver.title != "Google Maps" or EC.presence_of_element_located((By.CLASS_NAME, "Io6YTe"))
        )
        soup = BeautifulSoup(driver.page_source, "lxml")

        if driver.title == "Google Maps":
            logging.warning(f"店家 URL {store_url} 載入失敗")
            return "未知店家名稱", "未知地址"

        meta_list = soup.find_all('meta')
        store_name = next((re.search('".*·', str(i)).group()[1:-2] for i in meta_list if 'itemprop="name"' in str(i) and re.search('".*·', str(i))), None)
        store_name = store_name or (driver.title.split(" - ")[0] if " - " in driver.title else "未知店家名稱")

        address_tag = soup.find('div', class_='Io6YTe')
        store_address = address_tag.text.strip() if address_tag else (
            soup.find('button', {'data-item-id': 'address'}).find('div', class_='Io6YTe').text.strip()
            if soup.find('button', {'data-item-id': 'address'}) else "未知地址"
        )

    except (TimeoutException, NoSuchElementException, Exception) as e:
        logging.error(f"提取店家 URL {store_url} 資訊失敗: {str(e)}")
        return "未知店家名稱", "未知地址"
    
    finally:
        driver.quit()

    return store_name, store_address

def get_interrelate_store_name(search_query, text_widget):
    global stop_flag
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.142 Safari/537.36")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    url = f'https://www.google.com.tw/maps/search/{search_query}'
    text_widget.insert(tk.END, f"正在搜尋: {search_query}\n")
    text_widget.see(tk.END)
    driver.get(url)

    store_dict = {}
    processed_urls = set()
    prev_store_count = 0

    try:
        WebDriverWait(driver, 10).until(
            lambda driver: (
                EC.presence_of_element_located((By.CLASS_NAME, "Nv2PK")) or
                EC.presence_of_element_located((By.CLASS_NAME, "Io6YTe"))
            )
        )
        text_widget.insert(tk.END, "頁面載入完成，開始提取店家資訊...\n")
        text_widget.see(tk.END)

        if stop_flag:
            text_widget.insert(tk.END, "因中止指令，提前結束店家提取\n")
            text_widget.see(tk.END)
            driver.quit()
            return store_dict

        if driver.find_elements(By.CLASS_NAME, "Nv2PK"):
            text_widget.insert(tk.END, "檢測到搜尋結果頁，開始監控店家數量...(如沒自動滑動請手動滑動頁面)\n")
            text_widget.see(tk.END)
            while True:
                if stop_flag:
                    text_widget.insert(tk.END, "因中止指令，結束店家數量監控\n")
                    text_widget.see(tk.END)
                    break
                places = driver.find_elements(By.CLASS_NAME, "Nv2PK")
                current_store_count = len(places)
                
                if current_store_count > prev_store_count:
                    text_widget.insert(tk.END, f"檢測到新店家數量: {current_store_count}，重新倒數 3 秒...\n")
                    text_widget.see(tk.END)
                    prev_store_count = current_store_count
                    for i in range(3, 0, -1):
                        text_widget.insert(tk.END, f"倒數 {i} 秒...\n")
                        text_widget.see(tk.END)
                        text_widget.update()
                        time.sleep(1)
                        if stop_flag:
                            text_widget.insert(tk.END, "因中止指令，中斷倒數\n")
                            text_widget.see(tk.END)
                            break
                else:
                    text_widget.insert(tk.END, f"店家數量無變化 ({current_store_count})，進入提取階段...\n")
                    text_widget.see(tk.END)
                    break

            if not stop_flag:
                total_stores = len(places)
                text_widget.insert(tk.END, f"總共找到 {total_stores} 家店家\n")
                text_widget.see(tk.END)
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {}
                    for idx, place in enumerate(places, 1):
                        if stop_flag:
                            text_widget.insert(tk.END, "因中止指令，停止提交新店家提取任務\n")
                            text_widget.see(tk.END)
                            break
                        try:
                            place_url = place.find_element(By.CLASS_NAME, "hfpxzc").get_attribute("href")
                            if place_url in processed_urls:
                                continue
                            text_widget.insert(tk.END, f"提交提取第 {idx}/{total_stores} 家店家: {place_url}...\n")
                            text_widget.see(tk.END)
                            futures[executor.submit(get_store_name_and_address, place_url)] = (idx, place_url)
                            processed_urls.add(place_url)
                        except Exception as e:
                            text_widget.insert(tk.END, f"提交第 {idx}/{total_stores} 家店家失敗: {str(e)}\n")
                            text_widget.see(tk.END)
                            logging.error(f"提交店家提取失敗: {str(e)}")

                    for future in futures:
                        if stop_flag:
                            text_widget.insert(tk.END, "因中止指令，停止等待店家提取結果\n")
                            text_widget.see(tk.END)
                            break
                        idx, place_url = futures[future]
                        try:
                            store_name, store_address = future.result()
                            store_id = re.search(r'0x[0-9a-f]{16}:0x[0-9a-f]{16}', place_url).group() if re.search(r'0x[0-9a-f]{16}:0x[0-9a-f]{16}', place_url) else "無ID"
                            store_dict[store_name] = (store_id, store_address, place_url)
                            text_widget.insert(tk.END, f"完成提取第 {idx}/{total_stores} 家店家: {store_name}\n")
                            text_widget.see(tk.END)
                        except Exception as e:
                            text_widget.insert(tk.END, f"提取第 {idx}/{total_stores} 家店家失敗: {str(e)}\n")
                            text_widget.see(tk.END)
                            logging.error(f"多商家提取失敗: {str(e)}")

        else:
            text_widget.insert(tk.END, "檢測到單一商家頁面\n")
            text_widget.see(tk.END)
            if not stop_flag:
                place_url = driver.current_url
                store_id = re.search(r'0x[0-9a-f]{16}:0x[0-9a-f]{16}', place_url).group() if re.search(r'0x[0-9a-f]{16}:0x[0-9a-f]{16}', place_url) else "無ID"
                store_name, store_address = get_store_name_and_address(place_url)
                store_dict[store_name] = (store_id, store_address, place_url)
                text_widget.insert(tk.END, f"已提取店家: {store_name}\n")
                text_widget.see(tk.END)

    except TimeoutException:
        text_widget.insert(tk.END, "頁面載入超時，可能無結果或被限制\n")
        text_widget.see(tk.END)
    except Exception as e:
        text_widget.insert(tk.END, f"發生錯誤: {str(e)}\n")
        text_widget.see(tk.END)
        logging.error(f"店家提取失敗: {str(e)}")

    finally:
        driver.quit()

    text_widget.insert(tk.END, f"總共收集 {len(store_dict)} 家店家\n")
    text_widget.see(tk.END)
    text_widget.update()
    return store_dict

def get_comment(store_url, store_name, store_address, target_reviews=0, text_widget=None):
    global stop_flag
    if not text_widget:
        text_widget = type('DummyText', (), {'insert': print, 'see': lambda x: None, 'update': lambda: None})()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.142 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    if not store_url or stop_flag:
        text_widget.insert(tk.END, f"{store_name}: 無有效 URL 或收到中止指令，無法提取評論\n")
        text_widget.see(tk.END)
        driver.quit()
        return []

    text_widget.insert(tk.END, f"{store_name}: 正在載入頁面 {store_url}...\n")
    text_widget.see(tk.END)
    driver.get(store_url)
    all_reviews = []

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(@aria-label, '評論') or contains(@aria-label, 'Reviews')]"))
        )
        if stop_flag:
            text_widget.insert(tk.END, f"{store_name}: 因中止指令，提前結束評論提取\n")
            text_widget.see(tk.END)
            driver.quit()
            return all_reviews

        review_tab = driver.find_element(By.XPATH, "//button[contains(@aria-label, '評論') or contains(@aria-label, 'Reviews')]")
        review_tab.click()
        text_widget.insert(tk.END, f"{store_name}: 成功點擊評論標籤\n")
        text_widget.see(tk.END)

        page_source = scroll_reviews(driver, store_name, target_reviews, text_widget)
        if page_source and not stop_flag:
            soup = BeautifulSoup(page_source, "lxml")
            all_reviews_html = soup.find_all(class_="jftiEf")
            text_widget.insert(tk.END, f"{store_name}: 總共找到 {len(all_reviews_html)} 則評論，開始篩選在地嚮導...\n")
            text_widget.see(tk.END)

            for review in all_reviews_html:
                if stop_flag:
                    text_widget.insert(tk.END, f"{store_name}: 因中止指令，中斷評論篩選\n")
                    text_widget.see(tk.END)
                    break
                if is_local_guide_html(review):
                    try:
                        name = review.find(class_="d4r55").text.strip() if review.find(class_="d4r55") else "未知用戶"
                        date = review.find(class_="rsqaWe").text.strip() if review.find(class_="rsqaWe") else "未知"
                        content = review.find(class_="wiI7pd").text.strip() if review.find(class_="wiI7pd") else "無內容"
                        stars = review.find(class_="kvMYJc").get("aria-label").strip().strip("顆星") if review.find(class_="kvMYJc") else "未知"

                        review_data = {
                            "店家名稱": store_name,
                            "店家地址": store_address,
                            "顧客名稱": name,
                            "評論日期": date,
                            "評論內容": content,
                            "評論星級": stars
                        }
                        all_reviews.append(review_data)

                        if target_reviews > 0 and len(all_reviews) >= target_reviews:
                            text_widget.insert(tk.END, f"{store_name}: 已達目標評論數 {target_reviews}\n")
                            text_widget.see(tk.END)
                            break
                    except Exception as e:
                        text_widget.insert(tk.END, f"{store_name}: 解析單則評論失敗: {str(e)}\n")
                        text_widget.see(tk.END)
                        logging.error(f"{store_name}: 解析單則評論失敗: {str(e)}")

            text_widget.insert(tk.END, f"{store_name}: 篩選完成，共收集 {len(all_reviews)} 則在地嚮導評論\n")
            text_widget.see(tk.END)
        else:
            text_widget.insert(tk.END, f"{store_name}: 未載入任何評論或因中止指令提前結束\n")
            text_widget.see(tk.END)

    except TimeoutException:
        text_widget.insert(tk.END, f"{store_name}: 頁面載入超時，可能被限制或無評論\n")
        text_widget.see(tk.END)
    except NoSuchElementException:
        text_widget.insert(tk.END, f"{store_name}: 未找到評論區域，可能頁面結構變化\n")
        text_widget.see(tk.END)
    except Exception as e:
        text_widget.insert(tk.END, f"{store_name}: 評論提取失敗: {str(e)}\n")
        text_widget.see(tk.END)
        logging.error(f"{store_name}: 評論提取失敗: {str(e)}")
    finally:
        driver.quit()

    return all_reviews

def stop_crawler(root, text_widget, progress_bar, save_path_var, run_button):
    global stop_flag, all_data
    stop_flag = True
    text_widget.insert(tk.END, "收到停止指令，正在終止爬蟲...\n")
    text_widget.see(tk.END)
    root.update()

    save_path = save_path_var.get()
    if all_data:
        try:
            df = pd.DataFrame(all_data, columns=["店家名稱", "店家地址", "顧客名稱", "評論日期", "評論星級", "評論內容"])
            df.to_csv(save_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
            text_widget.insert(tk.END, f"已儲存目前爬取的資料到: {save_path}\n")
            text_widget.see(tk.END)
            messagebox.showinfo("停止", f"爬蟲已停止！\n目前資料已儲存到: {save_path}")
        except PermissionError as e:
            text_widget.insert(tk.END, f"儲存檔案失敗: 權限問題，請確保檔案未被占用\n")
            text_widget.see(tk.END)
            messagebox.showerror("錯誤", f"儲存檔案失敗！\n{e}")
    else:
        text_widget.insert(tk.END, "目前尚未爬取任何評論，無資料可儲存\n")
        text_widget.see(tk.END)
        messagebox.showinfo("停止", "爬蟲已停止！\n目前無資料儲存")

    progress_bar['value'] = 0
    run_button.config(state="normal")
    stop_button.config(state="disabled")
    text_widget.insert(tk.END, "爬蟲已完全停止並重置\n")
    text_widget.see(tk.END)
    root.update()

def run_crawler(root, region_entry, category_entry, reviews_entry, text_widget, progress_bar, save_path_var, run_button):
    global stop_flag, all_data
    stop_flag = False
    all_data = []
    text_widget.delete(1.0, tk.END)
    text_widget.insert(tk.END, "正在後台執行，請稍候...\n")
    text_widget.see(tk.END)
    progress_bar['value'] = 0
    text_widget.update()
    run_button.config(state="disabled")

    region = region_entry.get().strip()
    category = category_entry.get().strip()
    target_reviews = reviews_entry.get().strip()

    try:
        target_reviews = int(target_reviews)
        if target_reviews < 0:
            raise ValueError("評論數量必須為非負數")
    except ValueError:
        text_widget.insert(tk.END, "輸入無效，預設為 0（蒐集所有評論）\n")
        text_widget.see(tk.END)
        target_reviews = 0

    if stop_flag:
        return

    search_query = f"{region} {category}" if category else region
    progress_bar['value'] = 10
    root.update()
    try:
        store_dict = get_interrelate_store_name(search_query, text_widget)
    except Exception as e:
        text_widget.insert(tk.END, f"搜尋店家失敗: {str(e)}\n")
        text_widget.see(tk.END)
        progress_bar['value'] = 100
        run_button.config(state="normal")
        root.update()
        time.sleep(0.5)
        progress_bar['value'] = 0
        return

    if stop_flag:
        return

    if not store_dict:
        text_widget.insert(tk.END, "未找到任何相關店家，程式結束。\n")
        text_widget.see(tk.END)
        progress_bar['value'] = 100
        run_button.config(state="normal")
        root.update()
        time.sleep(0.5)
        progress_bar['value'] = 0
        return

    total_stores = len(store_dict)
    progress_step = max(80 / total_stores, 1)

    for idx, (store_name, (store_id, store_address, store_url)) in enumerate(store_dict.items(), 1):
        if stop_flag:
            text_widget.insert(tk.END, f"停止於第 {idx}/{total_stores} 家店家處理前\n")
            text_widget.see(tk.END)
            break
        text_widget.insert(tk.END, f"正在處理店家: {store_name} ({idx}/{total_stores})\n")
        text_widget.see(tk.END)
        reviews = get_comment(store_url, store_name, store_address, target_reviews, text_widget)
        all_data.extend(reviews)
        progress_bar['value'] = 10 + (idx * progress_step)
        root.update()

    if not stop_flag:
        if all_data:
            save_path = save_path_var.get()
            try:
                progress_bar['value'] = 95
                root.update()
                df = pd.DataFrame(all_data, columns=["店家名稱", "店家地址", "顧客名稱", "評論日期", "評論星級", "評論內容"])
                df.to_csv(save_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
                text_widget.insert(tk.END, f"爬取完成！資料已保存到: {save_path}\n")
                text_widget.see(tk.END)
                messagebox.showinfo("完成", f"爬取完成！\n資料已保存到: {save_path}")
            except PermissionError as e:
                text_widget.insert(tk.END, f"儲存檔案失敗: 權限問題，請確保檔案未被占用\n")
                text_widget.see(tk.END)
                messagebox.showerror("錯誤", f"儲存檔案失敗！\n{e}")
        else:
            text_widget.insert(tk.END, "未找到任何在地嚮導評論\n")
            text_widget.see(tk.END)
            messagebox.showinfo("完成", "未找到任何在地嚮導評論！")

        progress_bar['value'] = 100
        text_widget.see(tk.END)
        root.update()
        time.sleep(0.5)
        progress_bar['value'] = 0
        
    run_button.config(state="normal")

def start_crawler(root, region_entry, category_entry, reviews_entry, text_widget, progress_bar, save_path_var, run_button, stop_button):
    if not save_path_var.get():
        messagebox.showwarning("警告", "請先選擇儲存路徑！")
        return
    stop_button.config(state="normal")
    thread = threading.Thread(target=run_crawler, args=(root, region_entry, category_entry, reviews_entry, text_widget, progress_bar, save_path_var, run_button))
    thread.start()

def select_save_path(save_path_var, save_entry, run_button):
    path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
    if path:
        save_path_var.set(path)
        save_entry.delete(0, tk.END)
        save_entry.insert(0, path)
        run_button.config(state="normal")

def create_gui():
    global stop_button
    root = tk.Tk()
    root.title("Google Maps 爬蟲工具")
    root.geometry("800x600")
    root.configure(bg="#e6e6e6")
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    main_frame = ttk.Frame(root, padding="15")
    main_frame.grid(row=0, column=0, sticky="nsew")
    main_frame.grid_rowconfigure(3, weight=1)
    main_frame.grid_columnconfigure(0, weight=1)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TLabel", font=("微軟正黑體", 12), background="#e6e6e6", foreground="#333333")
    style.configure("TButton", font=("微軟正黑體", 12), padding=6, background="#4CAF50", foreground="white")
    style.map("TButton", background=[('active', '#45a049')])
    style.configure("red.TButton", font=("微軟正黑體", 12), padding=6, background="#f44336", foreground="white")
    style.map("red.TButton", background=[('active', '#d32f2f')])
    style.configure("TEntry", font=("微軟正黑體", 12), padding=5)
    style.configure("green.Horizontal.TProgressbar", troughcolor="#d9d9d9", background="#4CAF50")

    input_frame = ttk.LabelFrame(main_frame, text=" 輸入參數 ", padding="10")
    input_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

    ttk.Label(input_frame, text="地區（如台南市中西區）:").grid(row=0, column=0, padx=5, pady=8, sticky="w")
    region_entry = ttk.Entry(input_frame, width=40)
    region_entry.grid(row=0, column=1, padx=5, pady=8, sticky="w")

    ttk.Label(input_frame, text="店家類型（如咖啡店）:").grid(row=1, column=0, padx=5, pady=8, sticky="w")
    category_entry = ttk.Entry(input_frame, width=40)
    category_entry.grid(row=1, column=1, padx=5, pady=8, sticky="w")

    ttk.Label(input_frame, text="每家店目標評論數（0 表示全部）:").grid(row=2, column=0, padx=5, pady=8, sticky="w")
    reviews_entry = ttk.Entry(input_frame, width=40)
    reviews_entry.grid(row=2, column=1, padx=5, pady=8, sticky="w")

    ttk.Label(input_frame, text="儲存 CSV 路徑:").grid(row=3, column=0, padx=5, pady=8, sticky="w")
    save_path_var = tk.StringVar()
    save_entry = ttk.Entry(input_frame, textvariable=save_path_var, width=30, state="readonly")
    save_entry.grid(row=3, column=1, padx=5, pady=8, sticky="w")
    save_button = ttk.Button(input_frame, text="選擇路徑", command=lambda: select_save_path(save_path_var, save_entry, run_button))
    save_button.grid(row=3, column=2, padx=5, pady=8)

    control_frame = ttk.Frame(main_frame)
    control_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
    run_button = ttk.Button(control_frame, text="執行", command=lambda: start_crawler(root, region_entry, category_entry, reviews_entry, text_widget, progress_bar, save_path_var, run_button, stop_button), state="disabled")
    run_button.pack(side=tk.LEFT, padx=5, pady=5)
    stop_button = ttk.Button(control_frame, text="停止", style="red.TButton", command=lambda: stop_crawler(root, text_widget, progress_bar, save_path_var, run_button), state="disabled")
    stop_button.pack(side=tk.LEFT, padx=5, pady=5)

    progress_bar = ttk.Progressbar(main_frame, length=700, mode='determinate', style="green.Horizontal.TProgressbar")
    progress_bar.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

    output_frame = ttk.LabelFrame(main_frame, text=" 執行進度 ", padding="10")
    output_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
    text_widget = tk.Text(output_frame, height=20, width=90, font=("微軟正黑體", 10), bg="#ffffff", fg="#333333", borderwidth=1, relief="solid")
    text_widget.pack(fill="both", expand=True)

    root.mainloop()

if __name__ == "__main__":
    create_gui()
