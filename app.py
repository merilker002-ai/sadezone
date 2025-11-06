import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO

# ======================================================================
# ⚙️ YARDIMCI FONKSİYONLAR
# ======================================================================

def find_header_row_revised(uploaded_file, max_rows_to_check=10):
    """
    Yüklenen dosyada başlık satırını bulur.
    """
    try:
        uploaded_file.seek(0)
        
        if uploaded_file.name.endswith('.csv'):
            content = uploaded_file.getvalue().decode("utf-8")
            df_temp = pd.read_csv(StringIO(content), header=None, nrows=max_rows_to_check, na_values=['#N/A', 'N/A', ' '])
        else:
            df_temp = pd.read_excel(uploaded_file, header=None, nrows=max_rows_to_check, na_values=['#N/A', 'N/A', ' '])
            
        for i in range(len(df_temp)):
            non_na_count = df_temp.iloc[i].count()
            if non_na_count > 1:
                row = df_temp.iloc[i].astype(str).values
                row_str = ' '.join(row).upper()
                
                if any(keyword in row_str for keyword in ['KARNE', 'VERİLEN', 'TAHAKKUK', 'SU MİKTARI', 'M3']):
                    return i
                    
        return 0
        
    except Exception:
        return 0

def load_simulation_data_revised(uploaded_file):
    """Yüklenen Zone dosyasını doğru başlık satırından okur."""
    if uploaded_file is None:
        return None

    uploaded_file.seek(0)
    header_index = find_header_row_revised(uploaded_file)
    
    st.sidebar.info(f"Tespit edilen başlık satırı indeksi: **{header_index+1}. satır**.")

    try:
        uploaded_file.seek(0)
        if uploaded_file.name.endswith('.csv'):
            content = uploaded_file.getvalue().decode("utf-8")
            df_raw = pd.read_csv(StringIO(content), header=header_index, na_values=['#N/A', 'N/A', ' ', 'nan'])
        else:
            df_raw = pd.read_excel(uploaded_file, header=header_index, na_values=['#N/A', 'N/A', ' ', 'nan'])
        
        return df_raw
    
    except Exception as e:
        st.error(f"Dosya Okuma Hatası: **{e}**")
        return None

def find_and_rename_columns_revised(df_raw):
    """Zone dosyasına özel sütunları eşleştirir."""
    
    # Sütun adlarını temizle
    df_raw.columns = df_raw.columns.astype(str).str.strip().str.replace('\n', ' ', regex=False)
    
    st.sidebar.write("📊 Mevcut Sütunlar:", df_raw.columns.tolist())
    
    column_mapping = {}
    found_columns = []
    
    for col in df_raw.columns:
        col_str = str(col).upper().strip()
        
        # 1. ZONE_ADI - Daha esnek eşleştirme
        if any(keyword in col_str for keyword in ['KARNE NO VE ADI', 'KARNE', 'ZONE', 'BÖLGE', 'ADI']):
            column_mapping[col] = 'ZONE_ADI'
            found_columns.append('ZONE_ADI')
        
        # 2. GIRN_SU_M3 - VERİLEN SU MİKTARI M3 sütunu
        elif any(keyword in col_str for keyword in ['VERİLEN SU MİKTARI M3', 'VERİLEN', 'GİREN', 'GIRN']):
            column_mapping[col] = 'GIRN_SU_M3'
            found_columns.append('GIRN_SU_M3')
        
        # 3. TAHAKKUK_M3 - TAHAKKUK M3 sütunu (doğru yazım)
        elif any(keyword in col_str for keyword in ['TAHAKKUK M3', 'TAHAKKUK', 'ÖLÇÜLEN']):
            column_mapping[col] = 'TAHAKKUK_M3'
            found_columns.append('TAHAKKUK_M3')
    
    st.sidebar.write("✅ Bulunan Sütunlar:", found_columns)
    return column_mapping

# ======================================================================
# 💧 SİMÜLASYON FONKSİYONLARI
# ======================================================================

def calculate_real_loss_percentage(boru_yasi, malzeme_kalitesi, sicaklik_stresi, basin_profili):
    """
    Gerçek Kayıp Yüzdesini hesaplar.
    """
    total_risk_score = boru_yasi + malzeme_kalitesi + sicaklik_stresi + basin_profili
    
    normalized_risk = (total_risk_score - 4) / (20 - 4)
    
    min_loss_percentage = 0.55
    max_loss_percentage = 0.75
    
    real_loss_percentage = min_loss_percentage + (max_loss_percentage - min_loss_percentage) * normalized_risk
    
    return real_loss_percentage

def calculate_losses(df, real_loss_percentage):
    """Verilen yüzdeye göre kayıp hacimlerini hesaplar."""
    df_calc = df.copy()
    
    # Önce gerekli sütunların var olduğundan emin olalım
    required_columns = ['TOPLAM_KACAK_M3']
    for col in required_columns:
        if col not in df_calc.columns:
            st.error(f"Hesaplama için gerekli sütun bulunamadı: {col}")
            st.error(f"Mevcut sütunlar: {list(df_calc.columns)}")
            return df_calc
    
    # Gerçek ve Görünür Kayıp Yüzdeleri
    df_calc['TAHMINI_GERCEK_KAYIP_YUZDESI'] = real_loss_percentage * 100
    df_calc['TAHMINI_GORUNUR_KAYIP_YUZDESI'] = (1 - real_loss_percentage) * 100
    
    # Hacim Hesaplamaları
    df_calc['TAHMINI_BORU_KAYBI_M3'] = df_calc['TOPLAM_KACAK_M3'] * real_loss_percentage
    df_calc['TAHMINI_SAYAC_KAYBI_M3'] = df_calc['TOPLAM_KACAK_M3'] * (1 - real_loss_percentage)

    # Yuvarlama
    cols_to_round = ['GIRN_SU_M3', 'TAHAKKUK_M3', 'TOPLAM_KACAK_M3', 'TAHMINI_BORU_KAYBI_M3', 'TAHMINI_SAYAC_KAYBI_M3']
    for col in cols_to_round:
        if col in df_calc.columns:
            df_calc[col] = df_calc[col].round(0).astype(int)

    return df_calc

# ======================================================================
# 🚀 STREAMLIT ARAYÜZÜ
# ======================================================================

st.set_page_config(
    page_title="Yüksek Kayıp Kaçak Analizi Simülatörü",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("💧 Kayıp Kaçak Analizi Simülatörü")
st.markdown("---")

# ---------------------------------------------
# 📥 Sidebar - Dosya Yükleme Alanı
# ---------------------------------------------
st.sidebar.header("Dosya Yükleme")
st.sidebar.markdown("Lütfen Zone (Bölge) Analiz verilerini içeren dosyanızı yükleyin (Giren Su ve Tahakkuk Miktarı olmalı).")

zone_file = st.sidebar.file_uploader(
    "Zone Analiz Dosyası Yükle",
    type=['xlsx', 'csv'],
    key='zone_file_uploader'
)

# ---------------------------------------------
# 1. Risk Parametreleri Tanımlama
# ---------------------------------------------
st.sidebar.header("⚙️ Altyapı ve Çevre Risk Parametreleri")

boru_malzemesi_options = {
    "Polietilen (PE/HDPE)": 1,
    "Beton/Betonarme (Çimento)": 3,
    "Sfero Döküm Demir": 3,
    "Gri Döküm (Font) Demir": 4,
    "Asbestli Çimento (AC)": 5
}
st.sidebar.subheader("I. Altyapı Parametreleri")

boru_yasi = st.sidebar.slider(
    "1. Boru Yaşı Endeksi", 
    min_value=1, max_value=5, value=5, step=1,
    help="1: Yeni (0-10 yıl), 5: Çok Eski (25+ yıl)"
)

malzeme_secimi = st.sidebar.selectbox(
    "2. Baskın Boru Malzemesi Kalitesi",
    options=list(boru_malzemesi_options.keys()),
    index=4
)
malzeme_kalitesi = boru_malzemesi_options[malzeme_secimi]

st.sidebar.subheader("II. Çevresel ve Operasyonel Parametreler")

sicaklik_stresi = st.sidebar.slider(
    "3. Zemin Hareketi/Sıcaklık Stresi", 
    min_value=1, max_value=5, value=4, step=1
)

basin_profili = st.sidebar.slider(
    "4. Basınç Profili", 
    min_value=1, max_value=5, value=5, step=1
)

# ---------------------------------------------
# 2. Dosya Okuma ve Veri İşleme
# ---------------------------------------------
df = None
if zone_file is not None:
    try:
        # Veriyi dosyadan oku
        df_raw = load_simulation_data_revised(zone_file) 
        
        if df_raw is not None:
            st.sidebar.write("📋 Ham Veri Önizleme:")
            st.sidebar.dataframe(df_raw.head(3))
            
            # Sütunları eşleştir
            column_mapping = find_and_rename_columns_revised(df_raw)
            
            if column_mapping:
                # DataFrame'i hazırla
                df = df_raw.rename(columns=column_mapping)
                
                # Gerekli sütunları kontrol et
                required_columns = ['ZONE_ADI', 'GIRN_SU_M3', 'TAHAKKUK_M3']
                available_columns = [col for col in required_columns if col in df.columns]
                
                st.sidebar.write("🔄 Kullanılabilir Sütunlar:", available_columns)
                
                if len(available_columns) == 3:
                    df = df[available_columns].copy()
                    
                    # TOPLAM satırlarını ve eksik ZONE_ADI olanları temizle
                    df = df.dropna(subset=['ZONE_ADI'])
                    df = df[~df['ZONE_ADI'].astype(str).str.contains('TOPLAM|TOTAL|GENEL', na=False, case=False)]
                    
                    # Sayısal dönüşüm ve temizlik
                    df['GIRN_SU_M3'] = pd.to_numeric(df['GIRN_SU_M3'], errors='coerce')
                    df['TAHAKKUK_M3'] = pd.to_numeric(df['TAHAKKUK_M3'], errors='coerce')
                    df = df.dropna(subset=['GIRN_SU_M3', 'TAHAKKUK_M3'])
                    
                    # Kaçak Hesaplaması - TOPLAM_KACAK_M3 sütununu oluştur
                    df['TOPLAM_KACAK_M3'] = df['GIRN_SU_M3'] - df['TAHAKKUK_M3']
                    df['TOPLAM_KACAK_M3'] = df['TOPLAM_KACAK_M3'].clip(lower=0)
                    
                    # Kayıp oranı hesaplama
                    df['TOPLAM_KACAK_ORANI'] = (df['TOPLAM_KACAK_M3'] / df['GIRN_SU_M3']) * 100
                    df.loc[df['GIRN_SU_M3'] <= 0, 'TOPLAM_KACAK_ORANI'] = 0
                    
                    st.success(f"✅ Zone Analiz verileri başarıyla yüklendi: **{len(df)}** bölge kaydı.")
                    st.sidebar.write("🔍 İşlenmiş Veri Önizleme:")
                    st.sidebar.dataframe(df.head())
                    
                else:
                    missing_cols = set(required_columns) - set(available_columns)
                    st.error(f"Eksik sütunlar: {missing_cols}")
                    st.info("Lütfen dosyanızın aşağıdaki sütunları içerdiğinden emin olun:")
                    st.write("- KARNE NO VE ADI (Zone Adı)")
                    st.write("- VERİLEN SU MİKTARI M3 (Giren Su)")
                    st.write("- TAHAKKUK M3 (Tahakkuk)")
            else:
                st.error("Sütun eşleştirme başarısız. Lütfen dosya formatını kontrol edin.")
                
    except Exception as e:
        st.error(f"İşlem hatası: {str(e)}")
        st.error(f"Hata türü: {type(e).__name__}")

# ---------------------------------------------
# 3. Hesaplama ve Sonuçları Gösterim
# ---------------------------------------------

if df is not None and not df.empty:
    
    # Önce DataFrame'in durumunu kontrol et
    st.write("📈 Veri Kontrolü:")
    st.write(f"- Toplam kayıt sayısı: {len(df)}")
    st.write(f"- Mevcut sütunlar: {list(df.columns)}")
    st.write(f"- TOPLAM_KACAK_M3 sütunu mevcut mu: {'TOPLAM_KACAK_M3' in df.columns}")
    
    if 'TOPLAM_KACAK_M3' in df.columns:
        st.write(f"- TOPLAM_KACAK_M3 değerleri: {df['TOPLAM_KACAK_M3'].tolist()}")
    
    # Eğer TOPLAM_KACAK_M3 sütunu yoksa, manuel olarak oluştur
    if 'TOPLAM_KACAK_M3' not in df.columns and 'GIRN_SU_M3' in df.columns and 'TAHAKKUK_M3' in df.columns:
        st.warning("TOPLAM_KACAK_M3 sütunu otomatik oluşturulamadı, manuel olarak oluşturuluyor...")
        df['TOPLAM_KACAK_M3'] = df['GIRN_SU_M3'] - df['TAHAKKUK_M3']
        df['TOPLAM_KACAK_M3'] = df['TOPLAM_KACAK_M3'].clip(lower=0)
        df['TOPLAM_KACAK_ORANI'] = (df['TOPLAM_KACAK_M3'] / df['GIRN_SU_M3']) * 100
        df.loc[df['GIRN_SU_M3'] <= 0, 'TOPLAM_KACAK_ORANI'] = 0
    
    # Gerçek Kayıp Yüzdesini Hesapla
    real_loss_percent_decimal = calculate_real_loss_percentage(boru_yasi, malzeme_kalitesi, sicaklik_stresi, basin_profili)
    real_loss_percent_display = round(real_loss_percent_decimal * 100, 1)

    # Kayıp Hacimlerini Hesapla
    try:
        df_results = calculate_losses(df, real_loss_percent_decimal)
        
        st.header("✨ Simülasyon Sonuçları ve Kayıp Dağılımı")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                label="Gerçek Kayıp Riski Puanı (Max 20)",
                value=f"{boru_yasi + malzeme_kalitesi + sicaklik_stresi + basin_profili}"
            )

        with col2:
            st.metric(
                label="Tahmini Boru Kaybı (Gerçek Kayıp) Oranı",
                value=f"%{real_loss_percent_display}"
            )

        with col3:
            st.metric(
                label="Tahmini İdari Kayıp (Görünür Kayıp) Oranı",
                value=f"%{100 - real_loss_percent_display:.1f}"
            )

        st.subheader("Bölge (Zone) Bazında Tahmini Kayıp Hacmi ($m^3$)")

        # Sonuç tablosu
        display_cols = ['ZONE_ADI', 'GIRN_SU_M3', 'TOPLAM_KACAK_M3', 'TOPLAM_KACAK_ORANI',
                        'TAHMINI_BORU_KAYBI_M3', 'TAHMINI_SAYAC_KAYBI_M3']
        
        # Sadece mevcut sütunları kullan
        available_display_cols = [col for col in display_cols if col in df_results.columns]
        display_df = df_results[available_display_cols].copy()
        
        # Sütun isimlerini Türkçe'ye çevir
        column_names_map = {
            'ZONE_ADI': 'Zone Adı',
            'GIRN_SU_M3': 'Giren Su (m³)',
            'TOPLAM_KACAK_M3': 'Toplam Kayıp (m³)',
            'TOPLAM_KACAK_ORANI': 'Toplam Kayıp (%)',
            'TAHMINI_BORU_KAYBI_M3': 'Tahmini Boru Kaybı (m³)',
            'TAHMINI_SAYAC_KAYBI_M3': 'Tahmini Sayaç/İdari Kayıp (m³)'
        }
        
        display_df.columns = [column_names_map.get(col, col) for col in display_df.columns]
        
        # Sayısal formatlama
        numeric_columns = ['Giren Su (m³)', 'Toplam Kayıp (m³)', 'Tahmini Boru Kaybı (m³)', 'Tahmini Sayaç/İdari Kayıp (m³)']
        for col in numeric_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")
        
        if 'Toplam Kayıp (%)' in display_df.columns:
            display_df['Toplam Kayıp (%)'] = display_df['Toplam Kayıp (%)'].round(2).astype(str) + '%'

        st.dataframe(display_df, use_container_width=True)

        # Toplam Özet
        if 'TAHMINI_BORU_KAYBI_M3' in df_results.columns and 'TAHMINI_SAYAC_KAYBI_M3' in df_results.columns:
            total_real_loss = df_results['TAHMINI_BORU_KAYBI_M3'].sum()
            total_apparent_loss = df_results['TAHMINI_SAYAC_KAYBI_M3'].sum()

            st.markdown("---")
            st.subheader("🔍 Eylem Planı Vurgusu")

            st.markdown(f"""
            Bu simülasyona göre:

            1.  **ACİL ALTYAPI İHTİYACI:** Toplam kayıp olan **{df_results['TOPLAM_KACAK_M3'].sum():,} m³'ün** **%{real_loss_percent_display}**'ü, yani **{total_real_loss:,} m³**, boru sızıntıları olarak tahmin edilmektedir.
            2.  **İDARİ MÜDAHALE İHTİYACI:** Geriye kalan **%{100 - real_loss_percent_display:.1f}**'ü, yani **{total_apparent_loss:,} m³**, sayaç hataları ve idari kayıplardan kaynaklanmaktadır.
            """)
        
    except Exception as e:
        st.error(f"Hesaplama hatası: {str(e)}")
        st.error("Lütfen veri formatını kontrol edin.")

else:
    st.info("Lütfen sol kenar çubuğundan Zone Analiz dosyanızı yükleyerek simülasyonu başlatın.")
