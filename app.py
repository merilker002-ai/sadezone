import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO # CSV dosyalarını işlemek için

# ======================================================================
# ⚙️ YARDIMCI FONKSİYONLAR (Dosya Okuma Robustluğu İçin)
# ======================================================================

def find_header_row_revised(uploaded_file, max_rows_to_check=10):
    """
    Yüklenen dosyada 'KARNE', 'VERİLEN', 'TAHAKKUK' anahtar kelimelerini içeren 
    başlık satırını dinamik olarak bulur.
    """
    try:
        uploaded_file.seek(0)
        
        # Dosya türüne göre okuma
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
                
                # Kritik anahtar kelimeler
                if any(keyword in row_str for keyword in ['KARNE', 'VERİLEN', 'TAHAKKUK', 'SU MİKTARI', 'M3']):
                    return i
                    
        return 0 # Bulunamazsa 0. satırı kullan
        
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
        st.error(f"Dosya Okuma Hatası: **{e}**. Lütfen dosya formatını kontrol edin.")
        return None

def find_and_rename_columns_revised(df_raw):
    """Zone dosyasına özel sütunları eşleştirir."""
    
    # Sütun adlarını temizle
    df_raw.columns = df_raw.columns.astype(str).str.strip().str.replace('\n', ' ', regex=False)
    
    column_mapping = {}
    
    for col in df_raw.columns:
        col_str = str(col).upper().strip()
        
        # 1. ZONE_ADI
        if 'KARNE NO VE ADI' in col_str or 'ZONE' in col_str or 'BÖLGE' in col_str:
            column_mapping[col] = 'ZONE_ADI'
        
        # 2. GIRN_SU_M3
        elif ('VERİLEN SU MİKTARI M3' in col_str or 'VERİLEN' in col_str or 'GİREN' in col_str or 'GIRN' in col_str) and 'TAHAKKUK' not in col_str:
            column_mapping[col] = 'GIRN_SU_M3'
        
        # 3. TAHAKKUK_M3
        elif 'TAHAKKUK M3' in col_str or 'TAHAKKUK' in col_str or 'ÖLÇÜLEN' in col_str:
            column_mapping[col] = 'TAHAKKUK_M3'
    
    return column_mapping

# ======================================================================
# 💧 SİMÜLASYON FONKSİYONLARI (Kullanıcının Verdiği Mantıkla)
# ======================================================================

def calculate_real_loss_percentage(boru_yasi, malzeme_kalitesi, sicaklik_stresi, basin_profili):
    """
    Kullanıcının slider girdilerine göre Gerçek Kayıp Yüzdesini hesaplar.
    Risk Puanı Aralığı: 4 (Min Risk) - 20 (Max Risk)
    Gerçek Kayıp % Aralığı: 55% - 75%
    """
    total_risk_score = boru_yasi + malzeme_kalitesi + sicaklik_stresi + basin_profili
    
    # Riski 4-20 aralığından 0-1 aralığına normalize etme:
    normalized_risk = (total_risk_score - 4) / (20 - 4)
    
    # Yüzdeyi 55% (min) ile 75% (max) arasına ölçekleme:
    min_loss_percentage = 0.55
    max_loss_percentage = 0.75
    
    real_loss_percentage = min_loss_percentage + (max_loss_percentage - min_loss_percentage) * normalized_risk
    
    return real_loss_percentage

def calculate_losses(df, real_loss_percentage):
    """Verilen yüzdeye göre kayıp hacimlerini hesaplar."""
    df_calc = df.copy()
    
    # Gerçek ve Görünür Kayıp Yüzdeleri
    df_calc['TAHMINI_GERCEK_KAYIP_YUZDESI'] = real_loss_percentage * 100
    df_calc['TAHMINI_GORUNUR_KAYIP_YUZDESI'] = (1 - real_loss_percentage) * 100
    
    # Hacim Hesaplamaları
    df_calc['TAHMINI_BORU_KAYBI_M3'] = df_calc['TOPLAM_KACAK_M3'] * real_loss_percentage
    df_calc['TAHMINI_SAYAC_KAYBI_M3'] = df_calc['TOPLAM_KACAK_M3'] * (1 - real_loss_percentage)

    # Yuvarlama
    cols_to_round = ['GIRN_SU_M3', 'TAHAKKUK_M3', 'TOPLAM_KACAK_M3', 'TAHMINI_BORU_KAYBI_M3', 'TAHMINI_SAYAC_KAYBI_M3']
    for col in cols_to_round:
        df_calc[col] = df_calc[col].round(0).astype(int)

    return df_calc

# ======================================================================
# 🚀 STREAMLIT ARAYÜZÜ (GÜNCEL)
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
st.sidebar.markdown("Puanları (1: Düşük Risk, 5: Yüksek Risk) seçin. Bu, toplam kayıp içindeki *Boru Kaybı* payını belirler.")

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
    help="1: Yeni (0-10 yıl), 5: Çok Eski (25+ yıl). Yaşlandıkça risk artar."
)

malzeme_secimi = st.sidebar.selectbox(
    "2. Baskın Boru Malzemesi Kalitesi",
    options=list(boru_malzemesi_options.keys()),
    index=4,
    help="Asbestli Çimento (5) en riskli, PE (1) en az riskli."
)
malzeme_kalitesi = boru_malzemesi_options[malzeme_secimi]

st.sidebar.subheader("II. Çevresel ve Operasyonel Parametreler")

sicaklik_stresi = st.sidebar.slider(
    "3. Zemin Hareketi/Sıcaklık Stresi", 
    min_value=1, max_value=5, value=4, step=1,
    help="1: Stabil/Ilıman, 5: Hareketli Zemin/Yüksek Sıcaklık Farkı. Stres arttıkça risk artar."
)

basin_profili = st.sidebar.slider(
    "4. Basınç Profili", 
    min_value=1, max_value=5, value=5, step=1,
    help="1: Düşük/Kontrollü Basınç, 5: Yüksek/Kontrolsüz Basınç. Basınç arttıkça sızıntı hacmi artar."
)


# ---------------------------------------------
# 2. Dosya Okuma ve Veri İşleme
# ---------------------------------------------
df = None
if zone_file is not None:
    # Veriyi dosyadan oku
    df_raw = load_simulation_data_revised(zone_file) 
    
    if df_raw is not None:
        # Sütunları eşleştir
        column_mapping = find_and_rename_columns_revised(df_raw)
        required_keys = ['ZONE_ADI', 'GIRN_SU_M3', 'TAHAKKUK_M3']
        
        if all(col in column_mapping.values() for col in required_keys):
            try:
                # DataFrame'i hazırla
                df = df_raw.rename(columns=column_mapping)
                df = df[required_keys].copy()
                
                # TOPLAM satırlarını ve eksik ZONE_ADI olanları temizle
                df = df.dropna(subset=['ZONE_ADI'])
                df = df[~df['ZONE_ADI'].astype(str).str.contains('TOPLAM|TOTAL|GENEL', na=False, case=False)]
                
                # Sayısal dönüşüm ve temizlik
                df['GIRN_SU_M3'] = pd.to_numeric(df['GIRN_SU_M3'], errors='coerce')
                df['TAHAKKUK_M3'] = pd.to_numeric(df['TAHAKKUK_M3'], errors='coerce')
                df = df.dropna(subset=['GIRN_SU_M3', 'TAHAKKUK_M3'])
                
                # Kaçak Hesaplaması - np.where yerine doğrudan pandas operasyonları kullan
                df['TOPLAM_KACAK_M3'] = df['GIRN_SU_M3'] - df['TAHAKKUK_M3']
                df['TOPLAM_KACAK_M3'] = df['TOPLAM_KACAK_M3'].clip(lower=0) # Negatif kaçakları 0 yap
                
                # Kayıp oranı hesaplama - np.where yerine doğrudan pandas
                df['TOPLAM_KACAK_ORANI'] = (df['TOPLAM_KACAK_M3'] / df['GIRN_SU_M3']) * 100
                df.loc[df['GIRN_SU_M3'] <= 0, 'TOPLAM_KACAK_ORANI'] = 0
                                                
                st.success(f"✅ Zone Analiz verileri başarıyla yüklendi ve işlendi: **{len(df)}** bölge kaydı.")

            except Exception as e:
                df = None
                st.error(f"Veri işleme ve hesaplama hatası: {e}")
                st.error(f"Hata detayı: {type(e).__name__}")
        else:
            st.error("Zone dosyasında gerekli sütunlar (ZONE, VERİLEN SU M3, TAHAKKUK M3) bulunamadı. Lütfen dosya içeriğini kontrol edin.")
            st.dataframe(df_raw.head())

# ---------------------------------------------
# 3. Hesaplama ve Sonuçları Gösterim
# ---------------------------------------------

if df is not None and not df.empty:
    
    # Gerçek Kayıp Yüzdesini Hesapla
    real_loss_percent_decimal = calculate_real_loss_percentage(boru_yasi, malzeme_kalitesi, sicaklik_stresi, basin_profili)
    real_loss_percent_display = round(real_loss_percent_decimal * 100, 1)

    # Kayıp Hacimlerini Hesapla
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
            value=f"%{real_loss_percent_display}",
            delta="Altyapı/Çevre Riskine Göre Belirlendi"
        )

    with col3:
        st.metric(
            label="Tahmini İdari Kayıp (Görünür Kayıp) Oranı",
            value=f"%{100 - real_loss_percent_display:.1f}",
            delta="Sayaç Hataları, Yasadışı Kullanım"
        )

    st.subheader("Bölge (Zone) Bazında Tahmini Kayıp Hacmi ($m^3$)")
    st.markdown("Toplam kayıp, belirlediğiniz risk parametrelerine göre **Boru Kaybı** ve **Sayaç Kaybı** olarak ayrılmıştır.")

    # Sonuç tablosu (gösterilecek sütunlar)
    display_cols = ['ZONE_ADI', 'GIRN_SU_M3', 'TOPLAM_KACAK_M3', 'TOPLAM_KACAK_ORANI',
                    'TAHMINI_BORU_KAYBI_M3', 'TAHMINI_SAYAC_KAYBI_M3']
    display_df = df_results[display_cols].copy()
    display_df.columns = ['Zone Adı', 'Giren Su (m³)', 'Toplam Kayıp (m³)', 'Toplam Kayıp (%)', 
                          'Tahmini Boru Kaybı (m³)', 'Tahmini Sayaç/İdari Kayıp (m³)']
    
    # Sayısal formatlama
    for col in ['Giren Su (m³)', 'Toplam Kayıp (m³)', 'Tahmini Boru Kaybı (m³)', 'Tahmini Sayaç/İdari Kayıp (m³)' ]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")
        
    display_df['Toplam Kayıp (%)'] = display_df['Toplam Kayıp (%)'].round(2).astype(str) + '%'

    st.dataframe(display_df, use_container_width=True)

    # Toplam Özet
    total_real_loss = df_results['TAHMINI_BORU_KAYBI_M3'].sum()
    total_apparent_loss = df_results['TAHMINI_SAYAC_KAYBI_M3'].sum()

    st.markdown("---")
    st.subheader("🔍 Eylem Planı Vurgusu")

    st.markdown(f"""
    Bu simülasyonda belirlenen risk parametrelerine göre (Risk Puanı: **{boru_yasi + malzeme_kalitesi + sicaklik_stresi + basin_profili}**):

    1.  **ACİL ALTYAPI İHTİYACI (Fiziksel Müdahale):** Toplam kayıp olan **{df_results['TOPLAM_KACAK_M3'].sum():,} $m^3$'ün** **%{real_loss_percent_display}**'ü, yani **{total_real_loss:,} $m^3$**, doğrudan **boru sistemi sızıntıları** olarak tahmin edilmektedir. Bu, acil **Basınç Yönetimi** ve **Şebeke Yenileme** ihtiyacını gösterir.
    2.  **İDARİ MÜDAHALE İHTİYACI (Görünür Kayıp):** Geriye kalan **%{100 - real_loss_percent_display:.1f}**'ü, yani **{total_apparent_loss:,} $m^3$**, **sayaç hataları, yasadışı kullanım ve idari kayıt eksikliklerinden** kaynaklanmaktadır. **Sayaç Değişimi/Kalibrasyonu** hemen önceliklendirilmelidir.
    """)
else:
    st.info("Lütfen sol kenar çubuğundan Zone Analiz dosyanızı yükleyerek simülasyonu başlatın.")
