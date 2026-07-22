# Audit: LLM vs Heuristic disagreements (228 / 620 criteria)
Tags:
- BUG_* = phat hien loi co the xac dinh ro
- OK_PARTIAL_MATCH_PLAUSIBLE = LLM override co co so (heuristic qua nghiem)
- REVIEW = can nguoi xem lai, khong the tu dong xac dinh dung/sai


## BUG_FULL_MATCH_UNDERSCORED (8)
- **cau_5_001__HS_2** / T5: text=`1055` | expected=`10 5 5` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí và tiêu chuẩn điểm bán phần, nên điểm chấm là 0/0.5.
- **cau_5_001__HS_9** / T5: text=`1055` | expected=`10 5 5` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí và tiêu chuẩn điểm bán phần, nên điểm chấm là 0/0.5.
- **cau_5_001__HS_15** / T5: text=`1055` | expected=`10 5 5` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí và tiêu chuẩn điểm bán phần, nên điểm chấm là 0/0.5.
- **cau_5_001__HS_18** / T5: text=`1055` | expected=`10 5 5` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí và tiêu chuẩn điểm bán phần, nên điểm chấm là 0/0.5.
- **cau_1_001__HS_24** / T1: text=`a: 35.29...` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã ghi đúng 2 con số trong kết quả chương trình, đáp ứng được điều kiện để được 0.25 điểm theo tiêu chí chấm điểm.
- **cau_1_001__HS_29** / T1: text=`a: 3.529......` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã viết đúng 3 chữ số đầu tiên của đáp án đúng là 3529, đủ điều kiện nhận 0.25 điểm theo tiêu chí chấm thi.
- **cau_5_001__HS_34** / T5: text=`1055` | expected=`10 5 5` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí và tiêu chuẩn điểm bán phần, nên điểm chấm là 0/0.5.
- **cau_5_001__HS_36** / T5: text=`1055` | expected=`10 5 5` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí và tiêu chuẩn điểm bán phần, nên điểm chấm là 0/0.5.

## BUG_FULL_MATCH_DOWNGRADED (1)
- **cau_3_001__HS_26** / T3: text=`a = 30 46817` | expected=`None` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.25/0.5
  - LLM: Học sinh chỉ sai 1 số trong đáp án, đáp ứng được điều kiện để được 0.25 điểm theo tiêu chí.

## BUG_HALLUCINATED_PARTIAL_MATCH (5)
- **cau_2_001__HS_3** / T2: text=`28` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra đúng 1 con số trong đáp án, tuy nhiên con số đó không chính xác theo tiêu chí chấm thi.
- **cau_5_001__HS_3** / T5: text=`9/113` | expected=`10 5 5` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã ghi đúng một con số trong đáp án kỳ vọng, đủ điều kiện nhận 0.25 điểm theo tiêu chí.
- **cau_2_001__HS_17** / T2: text=`8-2` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra được một con số trong kết quả chính xác, đáp ứng được điều kiện để nhận 0.25 điểm theo quy tắc điểm bán phần.
- **cau_2_001__HS_34** / T2: text=`26` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra đúng 1 con số, tuy nhiên con số đó không khớp với đáp án kỳ vọng.
- **cau_2_001__HS_36** / T2: text=`26` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra đúng 1 con số, tuy nhiên con số đó không khớp với đáp án kỳ vọng.

## OK_PARTIAL_MATCH_PLAUSIBLE (34)
- **cau_1_001__HS_2** / T1: text=`3.5 16` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng 1 con số trong 4 con số cần tìm, đáp ứng được 1/4 tiêu chí.
- **cau_12_001__HS_2** / T12: text=`a: 112024` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã nhập đúng tháng và năm, nhưng sai ngày. Do đó, đáp án của họ chỉ là một phần của đáp án đúng.
- **cau_2_001__HS_7** / T2: text=`12÷48` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã thực hiện đúng 1 con số trong câu hỏi, đó là số 12. Theo quy tắc điểm bán phần, nếu đúng 1 con số thì được 0.25 điểm.
- **cau_12_001__HS_7** / T12: text=`7.1.1.2026.` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.5/0.5
  - LLM: Học sinh đã đúng tháng và năm, nhưng sai ngày. Do đó, đáp án chỉ đạt được 50% điểm.
- **cau_1_001__HS_9** / T1: text=`a: 352.516` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng 3 con số trong đáp án, đáp ứng được điều kiện để được 0.25 điểm theo tiêu chí.
- **cau_12_001__HS_9** / T12: text=`a: 7112026` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng tháng và năm, nhưng sai ngày. Theo tiêu chí, họ sẽ được 0.25 điểm.
- **cau_2_001__HS_10** / T2: text=`a: 2 - 1 128` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã sử dụng một con số đúng trong biểu thức của họ, đáp ứng điều kiện để được thưởng 0.25 điểm. Tuy nhiên, biểu thức của họ không khớp với tiêu chí chấm thi.
- **cau_12_001__HS_10** / T12: text=`a: 10.1.12.1.20.25` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng tháng và năm, nhưng sai ngày.
- **cau_6_001__HS_12** / T6: text=`4532` | expected=`4` | heuristic=0.0 (No output token correct.) -> llm=0.5/0.5
  - LLM: Học sinh chỉ đưa ra đúng một số trong đáp án kỳ vọng, còn lại đều sai. Tuy nhiên, đáp án của học sinh vẫn khớp với tiêu chí chấm thi yêu cầu đáp án luôn là 4.
- **cau_1_001__HS_15** / T1: text=`352.57` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đúng 3 con số trong đáp án 3529, đạt được 0.25 điểm theo tiêu chí.
- **cau_5_001__HS_17** / T5: text=`là: 10.53` | expected=`10 5 5` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra đúng một con số trong ba con số cần thiết, nhưng sai ở hai con số khác.
- **cau_12_001__HS_17** / T12: text=`24/7/2026` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã ghi đúng tháng và năm, tuy nhiên lại sai ngày. Theo quy tắc điểm bán phần, học sinh được 0.25 điểm.
- **cau_1_001__HS_18** / T1: text=`352.510...` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng một con số trong đáp án 3529, đáp ứng tiêu chí 'Đúng 2 hoặc 3 con số thì được 0.25 điểm'.
- **cau_12_001__HS_18** / T12: text=`a: 71.5.1.20.27` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng tháng và năm trong ngày tháng, nhưng sai cấu trúc đầu vào và ngày.
- **cau_1_001__HS_19** / T1: text=`35.2510...` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng một số 2510 trong đáp án, đủ điều kiện nhận 0.25 điểm theo tiêu chí.
- **cau_2_001__HS_19** / T2: text=`a: .128` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng 1 con số trong đáp án, tuy nhiên cần viết đầy đủ cả cột a và cột b với giá trị đúng là 12 và -4 để đạt được điểm tối đa.
- **cau_1_001__HS_21** / T1: text=`352.59` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng 1 con số trong đáp án 3529, đáp ứng được điều kiện được 0.25 điểm khi đúng 2 hoặc 3 con số.
- **cau_2_001__HS_21** / T2: text=`12-9` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng 1 con số trong kết quả chương trình theo yêu cầu, do đó họ được 0.25 điểm.
- **cau_5_001__HS_21** / T5: text=`là: 1011` | expected=`10 5 5` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra đúng 1 con số trong 3 con số cần tìm, tuy nhiên đã sai 2 con số và đưa ra một con số không liên quan.
- **cau_12_001__HS_24** / T12: text=`a: 10.1.1.2026.` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã ghi đúng tháng và năm, nhưng sai ngày. Theo quy tắc điểm bán phần, họ được 0.25 điểm.
- **cau_1_001__HS_26** / T1: text=`352510` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng 3 con số trong đáp án 3529, đủ điều kiện nhận 0.25 điểm theo quy định.
- **cau_2_001__HS_26** / T2: text=`lai: -4+2` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã thực hiện đúng phép tính cộng nhưng kết quả sai so với đáp án kỳ vọng.
- **cau_5_001__HS_26** / T5: text=`1052` | expected=`10 5 5` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã ghi đúng 1 con số trong ba con số cần ghi, đạt được 1/3 điểm theo tiêu chí. Tuy nhiên, tiêu chí chấm điểm chỉ thưởng 0.25 điểm nếu học sinh ghi đúng 2 con số.
- **cau_1_001__HS_28** / T1: text=`352, 510...` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đáp ứng được điều kiện được 0.25 điểm khi đúng 2 con số.
- **cau_5_001__HS_28** / T5: text=`155` | expected=`10 5 5` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chưa ghi đúng cả ba con số trong đáp án kỳ vọng, nhưng đã ghi đúng một con số. Theo tiêu chí chấm điểm, học sinh được 0.25 điểm nếu đúng 2 con số, tuy nhiên trong trường hợp này chỉ đúng 1 con số.
- **cau_10_001__HS_29** / T10: text=`10-1-2 10-1-2-1-9-1-1-1` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng một vị trí trong đáp án, nhưng sai ở 8/10 vị trí. Do sai sót giới hạn trong 2/10 đầu và 6/10 cuối nên vẫn đủ điều kiện nhận được 0.25 điểm.
- **cau_12_001__HS_29** / T12: text=`28/1/2026` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.5/0.5
  - LLM: Học sinh đã in ra đúng tháng và năm, nhưng sai ngày. Dựa trên quy tắc điểm bán phần, học sinh được 0.25 điểm. Tuy nhiên, do sai ngày, bài làm không đạt được yêu cầu đầy đủ, nên điểm dự kiến là 0.25/0.5 = 0.5.
- **cau_1_001__HS_30** / T1: text=`352.510` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng 2/4 con số trong đáp án, đáp ứng được 50% tiêu chí.
- **cau_2_001__HS_30** / T2: text=`l: 12` | expected=`12 -4` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã ghi đúng một con số trong đáp án, tuy nhiên chưa ghi cả hai con số 12 và -4 như yêu cầu.
- **cau_12_001__HS_32** / T12: text=`28.1.12.1.202` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng tháng và năm với đáp án kỳ vọng, nhưng sai ngày.
- **cau_1_001__HS_36** / T1: text=`352.510` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng 2/4 con số trong đáp án, đáp ứng được 0.25 điểm theo tiêu chí.
- **cau_12_001__HS_36** / T12: text=`là: 10/1/2026` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.5/0.5
  - LLM: Học sinh đã ghi đúng cả ngày, tháng và năm theo tiêu chí chấm thi và đáp án kỳ vọng.
- **cau_1_001__HS_39** / T1: text=`352.59` | expected=`3529` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng 1 con số trong đáp án 3529, đáp ứng được điều kiện được 0.25 điểm khi đúng 2 hoặc 3 con số.
- **cau_12_001__HS_39** / T12: text=`10/1/20` | expected=`10/1/2026` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã in ra đúng ngày và năm, tuy nhiên lại sai về format tháng.

## REVIEW (180)
- **cau_11_001__HS_2** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_2** / T13A1: text=`bool isPrime(int n) {   for(int i = 0; i < n; i++) {     if(n % i == 0) return 0;   }   return 1;   if(n < 2) return 0;   if(n != 2 && n % 2 == 0) return 0;   for(int i = 3; i * i <= n; i++) {     if(n % i == 0) return 0;   }   return 1;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã đáp ứng được tiêu chí kiểm tra số nguyên tố.
- **cau_13__HS_2** / T13B: text=`bool isPrime(int n) {
  for(int i = 0; i < n; i++) {
    if(n % i == 0) return 0;
  }
  return 1;
  if(n < 2) return 0;
  if(n != 2 && n % 2 == 0) return 0;
  for(int i = 3; i * i <= n; i++) {
    if(n % i == 0) return 0;
  }
  return 1;
int main()
{
    int a[MAX], n=0;
    NhapMang(a,n);
    cout << SumPrime(a,n) << endl;
    int max = findMax(a,n);
    cout << findMin(a,n,max) << endl;
    return 0;
}` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã đáp ứng được yêu cầu tìm vị trí phần tử có giá trị lớn nhất đầu tiên trong mảng sử dụng điều kiện a[i] > a[m].
- **cau_13__HS_2** / T13C1: text=`int main() {     int a[MAX], n=0;     NhapMang(a,n);     cout << SumPrime(a,n) << endl;     int max = findMax(a,n);     cout << findMin(a,n,max) << endl;     return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã định nghĩa hàm `TongSNT(a,n)` đúng cách nhưng quên in kết quả ra màn hình.
- **cau_13__HS_2** / T13C2: text=`int main() {     int a[MAX], n=0;     NhapMang(a,n);     cout << SumPrime(a,n) << endl;     int max = findMax(a,n);     cout << findMin(a,n,max) << endl;     return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.125/0.25
  - LLM: Học sinh đã gọi đúng hàm để tìm giá trị lớn nhất nhưng lại bỏ qua việc in ra kết quả.
- **cau_14__HS_2** / T14A: text=`char MaSV[20]; char HoTen[50]; int NamSinh;` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng đầy đủ các tiêu chí đã cho, khai báo struct Sinhvien với đúng tên và kiểu dữ liệu các thuộc tính như yêu cầu.
- **cau_14__HS_2** / T14B1: text=`void NhapSV(SinhVien &a) cin.ignore(); fgets(a.HoTen, 50, stdin); cin.ignore(); fgets(a.NamSinh, 50, stdin); cin.ignore();` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã truyền tham chiếu đúng đối với đối tượng SinhVien, tuy nhiên tiêu chí yêu cầu kiểm tra việc truyền cả tham chiếu và biến x. Do đó, họ sẽ bị trừ 0.25 điểm không cần thiết.
- **cau_15__HS_2** / T15B1: text=`R1C1=6 t8 cleu=6 chan=18 | R1C2=3-3 ngvui=3 ngua=3 | R2C1=12-30 cleu=12 chan=30 | R2C2=5-9 ngvui=3 ngua=9 | R3C1=8-10 cleu=8 chan=40 | R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.0417/0.0833
  - LLM: Học sinh đáp ứng tiêu chí ở hai trong ba dòng, với một sai lầm ở dòng thứ ba. Do đó, họ đạt được một nửa yêu cầu.
- **cau_15__HS_2** / T15B2: text=`R1C1=6 t8 cleu=6 chan=18 | R1C2=3-3 ngvui=3 ngua=3 | R2C1=12-30 cleu=12 chan=30 | R2C2=5-9 ngvui=3 ngua=9 | R3C1=8-10 cleu=8 chan=40 | R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0833/0.0833
  - LLM: Bài làm học sinh đã đáp ứng tiêu chí ở hầu hết các trường hợp input, trừ một lỗi nhỏ ở R3C1. Do đó, điểm dự kiến là 0.8258.
- **cau_15__HS_2** / T15B3: text=`R1C1=6 t8 cleu=6 chan=18 | R1C2=3-3 ngvui=3 ngua=3 | R2C1=12-30 cleu=12 chan=30 | R2C2=5-9 ngvui=3 ngua=9 | R3C1=8-10 cleu=8 chan=40 | R3C2=giả định sai` | expected=`None` | heuristic=0.0417 (1/2 expected values found at row R3.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã đưa ra kết quả chính xác cho hầu hết các trường hợp input và chỉ sai một trường hợp duy nhất.
- **cau_15__HS_2** / T15C1: text=`int clau, chan, ngua;
Input: nhap dau 6 clau = 6
nhap chau 10 chan = 10
Output: Ngua = 3
Ngua = 3` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã đưa ra hệ số cho 'clau' và 'chan', có thể coi là bước đầu tiên hướng tới hệ phương trình. Tuy nhiên, họ chưa đưa ra hệ phương trình X + Y = N và 2X + 4Y = M như tiêu chí yêu cầu.
- **cau_15__HS_2** / T15C3: text=`int clau, chan, ngua;
Input: nhap dau 6 clau = 6
nhap chau 10 chan = 10
Output: Ngua = 3
Ngua = 3` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng đúng tên biến và đầu vào, nhưng công thức tính X lại sai so với yêu cầu.
- **cau_15__HS_2** / T15C4: text=`int clau, chan, ngua;
Input: nhap dau 6 clau = 6
nhap chau 10 chan = 10
Output: Ngua = 3
Ngua = 3` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã áp dụng đúng công thức tính số ngựa theo tiêu chí chấm điểm.
- **cau_13__HS_3** / T13A1: text=`int main()
{
    int a[MAX], n=0;
    NhapMang(a,n);` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.5
  - LLM: Học sinh đã viết đúng cơ bản của hàm KiemtraSNT, tuy nhiên chưa sử dụng đúng cách trong main do chưa nhập giá trị n cho mảng a.
- **cau_13__HS_3** / T13B: text=`int main()
{
    int a[MAX], n=0;
    NhapMang(a,n);` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã thực hiện đúng yêu cầu tìm vị trí phần tử có giá trị lớn nhất đầu tiên trong mảng.
- **cau_14__HS_3** / T14C: text=`void InDSSV(Sinhvien a[], int n) for(int i;i<n;i++){ y(Sinhvien.NoiSinhOa[i]=='TPHCM'); x=...; else x=0; switch(x){ case 1: cout<<SinhVien; case 0: break;` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.125/0.25
  - LLM: Học sinh đã đáp ứng được 1/2 yêu cầu của tiêu chí bởi họ sử dụng đúng kiểu so sánh == cho chuỗi string. Tuy nhiên, họ sử dụng thêm biến y để quyết định in hay không in thông tin sinh viên, thay vì chỉ in thông tin khi thỏa mãn điều kiện.
- **cau_15__HS_3** / T15A1: text=`số chẵn input: N, M là số nguyên dương output: kết luận cuối sau tính toán để khẳng định / phủ định giả thiết trên` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.125/0.125
  - LLM: Học sinh đã sử dụng input để đưa ra câu hỏi và tính toán kết luận cuối, tuy nhiên chưa đáp ứng được tiêu chí về 'không âm'.
- **cau_15__HS_3** / T15A2: text=`số chẵn input: N, M là số nguyên dương output: kết luận cuối sau tính toán để khẳng định / phủ định giả thiết trên` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.125/0.125
  - LLM: Học sinh đáp ứng được tiêu chí về output là hai số nguyên, tuy nhiên chưa nhất quán với câu c về việc chọn không âm.
- **cau_15__HS_3** / T15B1: text=`R1C1=6 | R1C2=18 | R2C1=20 | R2C2=45 | R3C1=10 | R3C2=18` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã thực hiện đúng yêu cầu ở dòng thứ nhất và dòng thứ hai của output. Tuy nhiên, họ đã nhập sai ở dòng thứ ba, nên không phải là dòng trống.
- **cau_15__HS_3** / T15B2: text=`R1C1=6 | R1C2=18 | R2C1=20 | R2C2=45 | R3C1=10 | R3C2=18` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã áp dụng logic đúng cho 2/3 số dòng, tuy nhiên chưa kiểm tra ví dụ 2 đối với dòng thứ nhất.
- **cau_15__HS_3** / T15B3: text=`R1C1=6 | R1C2=18 | R2C1=20 | R2C2=45 | R3C1=10 | R3C2=18` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R3.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã đưa ra output 'giả định sai' đúng với tiêu chí chấm thi cho input 9 10.
- **cau_15__HS_3** / T15C1: text=`[box 1] giá trị không sai [diamond 2] N, M 1 -> 2` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã cố gắng đưa ra hệ phương trình đúng dạng nhưng chưa đáp ứng được tiêu chí về giá trị của N và M.
- **cau_15__HS_3** / T15C2: text=`[box 1] giá trị không sai [diamond 2] N, M 1 -> 2` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.2/0.2
  - LLM: Học sinh đã nỗ lực đưa ra điều kiện giả định sai nhưng chưa kiểm chứng kỹ lưỡng.
- **cau_15__HS_3** / T15C3: text=`[box 1] giá trị không sai [diamond 2] N, M 1 -> 2` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng ký hiệu biến đúng nhưng chưa áp dụng công thức để tính số người X.
- **cau_15__HS_3** / T15C4: text=`[box 1] giá trị không sai [diamond 2] N, M 1 -> 2` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã đáp ứng đầy đủ tiêu chí, tính đúng số ngựa Y theo công thức Y = M/2 - N và cung cấp một giá trị đúng theo yêu cầu.
- **cau_13__HS_7** / T13A1: text=`bool nt(int n) if (n < 2) return false; for (int i = 2; i <= n; i++) if (n % i == 0) return false; return true; int tong(int a[1], int n) int tam = 0; for (int i = 0; i < n; i++) if (nt(a[i])) tam = tam + a[i]; return tam;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã thực hiện đúng yêu cầu của tiêu chí đối với hàm KiemtraSNT, nên có thể dự kiến được 0.5 điểm cho phần này.
- **cau_13__HS_7** / T13A2: text=`bool nt(int n) if (n < 2) return false; for (int i = 2; i <= n; i++) if (n % i == 0) return false; return true; int tong(int a[1], int n) int tam = 0; for (int i = 0; i < n; i++) if (nt(a[i])) tam = tam + a[i]; return tam;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Bài làm học sinh đã đúng với yêu cầu tính tổng các số nguyên tố trong mảng với trọng số là giá trị của chúng.
- **cau_13__HS_7** / T13B: text=`int vi.tri.(int a[], int n) int ma = a[0]; for (int i = 1; i < n; i++) ma = max(ma, a[i]); for (int i = 0; i < n; i++)` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.0/0.5
  - LLM: Học sinh chưa đáp ứng được tiêu chí tìm vị trí phần tử có giá trị lớn nhất đầu tiên trong mảng.
- **cau_13__HS_7** / T13C1: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout<<tong(a,n)<<endl; cout<<vi.tri(a,n); }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được 1/2 tiêu chí yêu cầu bằng cách viết hàm tính tổng các số nguyên tố và sử dụng hàm này để in kết quả. Tuy nhiên, tên hàm không chính xác và chưa đáp ứng được tiêu chí in vị trí của số nguyên tố lớn nhất.
- **cau_14__HS_7** / T14A: text=`struct SinhVien char MaSV[30]; char HoTen[255]; int NamSinh; char NoiSinh[255]; float DTB DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã khai báo struct SinhVien với đúng tên và kiểu dữ liệu các thuộc tính như yêu cầu.
- **cau_14__HS_7** / T14B1: text=`void NhapSV(SinhVien &t) cin>>t.MaSV; cin.getline(t.HoTen,254); cin>>t.NamSinh;cin.ignore(); cin.getline(t.NoiSinh,254); cin>>t.DTB;` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh chưa đáp ứng được yêu cầu về việc truyền tham trị đối với đối tượng Sinhvien.
- **cau_14__HS_7** / T14B2: text=`void NhapSV(SinhVien &t) cin>>t.MaSV; cin.getline(t.HoTen,254); cin>>t.NamSinh;cin.ignore(); cin.getline(t.NoiSinh,254); cin>>t.DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được 2/4 yêu cầu về việc nhập thông tin có khoảng trắng bằng cách sử dụng hàm getline để nhập tên và nơi sinh. Tuy nhiên, họ vẫn sử dụng cin>> để nhập mã sinh viên và điểm trung bình, không đáp ứng được 1/4 yêu cầu còn lại.
- **cau_14__HS_7** / T14C: text=`void InDSSV(Sinhvien a[], int n) {     for (int i=0; i<n; i++)         if (strcmp(a[i].NoiSinh, "TPHCM") == 0)             cout << a[i].MaSV << endl;             cout << a[i].Hoten << endl;             cout << a[i].NamSinh << endl;             cout << a[i].NoiSinh << endl;             cout << a[i].DTB << endl;` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.2/0.25
  - LLM: Học sinh đáp ứng được yêu cầu in thông tin sinh viên có NoiSinh là 'TPHCM' nhưng lại in cả thông tin không cần thiết.
- **cau_15__HS_7** / T15A1: text=`int N; // so dau bien N co kieu int de mo ta so luong chau ta m int M; // bien M co kieu int de mo ta so luong chien ca mot so nguyen int d nguyet; // bien nguyet kieu int luu ket qua cho 80 nguoi tinh du lieu de bai int ngua; // bien ngua kieu int luu ket qua chu 80 ngua tinh duoc tu de bai` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.125/0.125
  - LLM: Học sinh đã định nghĩa các biến cần thiết nhưng chưa kiểm tra N và M là không âm.
- **cau_15__HS_7** / T15B1: text=`R1C1=N=6, M=18 | R1C2=nguoi=8, ngua=8 | R2C1=N=220, M=680 | R2C2=nguoi=100, ngua=120 | R3C1=N=6, M=11 | R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã áp dụng đúng quy luật từ ví dụ được cung cấp trong 2/3 trường hợp.
- **cau_15__HS_7** / T15B2: text=`R1C1=N=6, M=18 | R1C2=nguoi=8, ngua=8 | R2C1=N=220, M=680 | R2C2=nguoi=100, ngua=120 | R3C1=N=6, M=11 | R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0278/0.0833
  - LLM: Học sinh đã thực hiện đúng hai trường hợp đầu tiên, nhưng trong trường hợp thứ hai, họ đã đưa ra kết quả sai và chưa đưa ra kết quả phù hợp với giả thiết 'người = 100, ngựa = 120'.
- **cau_15__HS_7** / T15B3: text=`R1C1=N=6, M=18 | R1C2=nguoi=8, ngua=8 | R2C1=N=220, M=680 | R2C2=nguoi=100, ngua=120 | R3C1=N=6, M=11 | R3C2=giả định sai` | expected=`None` | heuristic=0.0417 (1/2 expected values found at row R3.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã đáp ứng đầy đủ tiêu chí bằng cách đưa ra các giá trị N và M đúng và đưa ra kết quả output phù hợp với giả định được đưa ra.
- **cau_15__HS_7** / T15C1: text=`[circle 1] Bắt đầu [parallelogram 2] Nhập N, M [rectangle 3] nguoi = (4*N - M)/2
ngua = (N - ngui) [diamond 4] N%2 == 0
M%2 == 0 [rectangle 5] nguoi = (4*N - M)/2
Xuat ngui va ngua
(nguoi + ngua == N)
& (2*nguoi + 4*ngua == M) [rectangle 6] Xuat 'gia dinh sai' 1 -> 2 2 -> 3 3 -> 4 4 -> 5: S 4 -> 6: S` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.08/0.1
  - LLM: Học sinh đã thực hiện hầu hết các bước cần thiết nhưng chưa sử dụng trực tiếp hệ phương trình X+Y=N, 2X+4Y=M.
- **cau_15__HS_7** / T15C2: text=`[circle 1] Bắt đầu [parallelogram 2] Nhập N, M [rectangle 3] nguoi = (4*N - M)/2
ngua = (N - ngui) [diamond 4] N%2 == 0
M%2 == 0 [rectangle 5] nguoi = (4*N - M)/2
Xuat ngui va ngua
(nguoi + ngua == N)
& (2*nguoi + 4*ngua == M) [rectangle 6] Xuat 'gia dinh sai' 1 -> 2 2 -> 3 3 -> 4 4 -> 5: S 4 -> 6: S` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.15/0.2
  - LLM: Học sinh đã tìm ra điều kiện giả định sai nhưng chưa hoàn toàn chính xác.
- **cau_15__HS_7** / T15C3: text=`[circle 1] Bắt đầu [parallelogram 2] Nhập N, M [rectangle 3] nguoi = (4*N - M)/2
ngua = (N - ngui) [diamond 4] N%2 == 0
M%2 == 0 [rectangle 5] nguoi = (4*N - M)/2
Xuat ngui va ngua
(nguoi + ngua == N)
& (2*nguoi + 4*ngua == M) [rectangle 6] Xuat 'gia dinh sai' 1 -> 2 2 -> 3 3 -> 4 4 -> 5: S 4 -> 6: S` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng đúng công thức để tính số người X theo tiêu chí đề ra và kiểm tra điều kiện N và M là số chẵn, cũng như điều kiện cuối để đảm bảo tính đúng số người.
- **cau_15__HS_7** / T15C4: text=`[circle 1] Bắt đầu [parallelogram 2] Nhập N, M [rectangle 3] nguoi = (4*N - M)/2
ngua = (N - ngui) [diamond 4] N%2 == 0
M%2 == 0 [rectangle 5] nguoi = (4*N - M)/2
Xuat ngui va ngua
(nguoi + ngua == N)
& (2*nguoi + 4*ngua == M) [rectangle 6] Xuat 'gia dinh sai' 1 -> 2 2 -> 3 3 -> 4 4 -> 5: S 4 -> 6: S` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng công thức nguoi = (4*N - M)/2 và ký hiệu biến khác, tuy nhiên công thức tính số ngựa Y chưa được sử dụng. Tuy nhiên, theo ghi chú của giáo viên, cho phép ký hiệu biến khác nhưng công thức phải đúng. Vì vậy, học sinh có thể nhận được điểm 0.1 nếu công thức tính số ngựa Y được thực hiện đúng theo tiêu chí.
- **cau_3_001__HS_9** / T3: text=`a = 28 24615` | expected=`None` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã sai 1 số trong đáp án, vì vậy họ được 0.25 điểm theo tiêu chí chấm thi.
- **cau_8__HS_9** / T8B: text=`0 505288 8 0 -6` | expected=`None` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.25
  - LLM: Học sinh đã đúng ít nhất 2 số trong đáp án kỳ vọng, đủ điều kiện để nhận điểm 0.25 theo tiêu chí chấm thi.
- **cau_10_001__HS_9** / T10: text=`10 9 8 7 6 5 4 3 2 1` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.15 (3/10 tokens correct (partial credit applied).) -> llm=0.2/0.5
  - LLM: Học sinh chỉ đúng 2 vị trí trong tổng số 10 vị trí yêu cầu.
- **cau_13__HS_9** / T13A1: text=`bool snt(int n) if(n < 2) return false; for(int i = 2; i <= n; i++) if(n % i == 0) return false; return true; int tongSnt(int a[], int n) int tong = 0; for(int i = 0; i < n; i++) if(snt(a[i]) == true) tong += a[i]; return tong;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã chính xác implement hàm snt để kiểm tra số nguyên tố, đáp ứng được tiêu chí chấm thi.
- **cau_13__HS_9** / T13A2: text=`bool snt(int n) if(n < 2) return false; for(int i = 2; i <= n; i++) if(n % i == 0) return false; return true; int tongSnt(int a[], int n) int tong = 0; for(int i = 0; i < n; i++) if(snt(a[i]) == true) tong += a[i]; return tong;` | expected=`None` | heuristic=0.25 (1/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã thực hiện đúng yêu cầu của tiêu chí, họ đã tạo ra hai hàm như yêu cầu và hàm tính tổng sử dụng đúng hàm kiểm tra số nguyên tố.
- **cau_13__HS_9** / T13B: text=`int max = a[0]; for (int i = 1; i < n; i++) if (a[i] > max) max = a[i];` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã sử dụng đúng logic để tìm vị trí phần tử có giá trị lớn nhất đầu tiên trong mảng, đáp ứng được yêu cầu của tiêu chí chấm thi.
- **cau_14__HS_9** / T14A: text=`struct SinhVien { char MaSV[10]; char HoTen[50]; int NamSinh; char NoiSinh[20]; float DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng 100% tiêu chí, khai báo struct Sinhvien với đúng tên và kiểu dữ liệu các thuộc tính.
- **cau_14__HS_9** / T14B1: text=`void NhapSV(Sinhvien &a) cin.getline(a.MaSV, 9); cin.getline(a.HoTen, 49); cin >> a.NamSinh; cin.ignore(); cin.getline(a.NoiSinh); cin >> a.DTB;` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Chưa có thông tin về cách sử dụng hàm NhapSV trong bài làm của học sinh, do đó không thể đưa ra quyết định về điểm số chính xác.
- **cau_14__HS_9** / T14B2: text=`void NhapSV(Sinhvien &a) cin.getline(a.MaSV, 9); cin.getline(a.HoTen, 49); cin >> a.NamSinh; cin.ignore(); cin.getline(a.NoiSinh); cin >> a.DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.1667/0.25
  - LLM: Học sinh đã đáp ứng 2/4 tiêu chí bằng cách sử dụng getline cho phần thông tin có khoảng trắng. Tuy nhiên, họ sử dụng cin>> cho 'NamSinh' và 'DTB', do đó không đáp ứng đầy đủ tiêu chí.
- **cau_14__HS_9** / T14C: text=`void InDSSV(Sinhvien a[], int n) {     for(int i = 0; i < n; i++) {         if (strcmp(a[i].NoiSinh, "TPHCM") == 0) {             cout << a[i].MaSV << " " << a[i].HoTen                 << a[i].NamSinh << " " << a[i].NoiSinh                 << a[i].DTB << endl;         }     }` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng đúng tiêu chí in thông tin sinh viên có NoiSinh là 'TPHCM'.
- **cau_15__HS_9** / T15B1: text=`R1C1=6 | R1C2=18 | R2C1=3 | R2C2=3 | R3C1=8 | R3C2=28 | R4C1=2 | R4C2=6 | R5C1=2 | R5C2=27` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã thực hiện đúng yêu cầu, nhập vào hai số nguyên và in ra hai dòng, mỗi dòng chứa hai phần tử, với tổng các phần tử trong mỗi dòng bằng nhau.
- **cau_15__HS_9** / T15B2: text=`R1C1=6 | R1C2=18 | R2C1=3 | R2C2=3 | R3C1=8 | R3C2=28 | R4C1=2 | R4C2=6 | R5C1=2 | R5C2=27` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã thực hiện đúng công thức tính nhưng chưa đáp ứng được yêu cầu về cách in kết quả.
- **cau_15__HS_9** / T15C3: text=`Biến n: N con tàu, Biến ngun: số người
Biến m: M con chân, Biến ngun: số người
Input: số nguyên n tàu, số nguyên m chân
Output: số nguyên người (biến người), số nguyên người hoặc "gia đình sai"` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng đúng công thức tính số người theo tiêu chí chấm điểm.
- **cau_11_001__HS_10** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_10** / T13B: text=`int VitriPhanTulnhat(int a[], int n) { for(int max_1 = a[0]; for(int i = 1; i < n; i++) if(a[i] > max_1)` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã tìm được vị trí phần tử lớn nhất đầu tiên nhưng cần kiểm tra lại việc sử dụng dấu '>' trong lệnh if.
- **cau_13__HS_10** / T13C1: text=`cout << "Tổng giá trị các phần tử là Số nguyên tố là:" << TonggianTo(a,n); cout << "Vị trí phần tử có giá trị là nhat đầu tiên trong mang là" << VtriPhanTuNhat(a,n) << endl;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã hoàn thành đầy đủ cả hai chức năng như yêu cầu và in kết quả ra màn hình với định dạng chính xác.
- **cau_13__HS_10** / T13C2: text=`cout << "Tổng giá trị các phần tử là Số nguyên tố là:" << TonggianTo(a,n); cout << "Vị trí phần tử có giá trị là nhat đầu tiên trong mang là" << VtriPhanTuNhat(a,n) << endl;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng chức năng TimMax(a,n) nhưng sử dụng tên hàm và biến khác. Tuy nhiên, tiêu chí chấm điểm chỉ yêu cầu in kết quả của hàm TimMax(a,n), không yêu cầu in kết quả của hai hàm TonggianTo(a,n) và VtriPhanTuNhat(a,n).
- **cau_14__HS_10** / T14B1: text=`void NhapSV(Sinhvien &a) cin >> a.MaSV; cin >> a.HoTen; cin >> a.NamSinh; cin >> a.NoSinh; cin >> a.DTB;` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh chưa truyền tham số đúng theo yêu cầu trong tiêu chí, họ sử dụng tham số &a thay vì &x.
- **cau_15__HS_10** / T15A1: text=`Input: nhập vào 2 số nguyên N và M (N là số cái đầu, M là số cái chân nhìn thấy được) Output: Nếu giả định thang có người hay ngựa nào, thì chân bao đầu là: 1. Nếu có người thì in ra số người và số ngựa. 2. Nếu không có người thì in ra "giả định sai"` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.125/0.125
  - LLM: Bài làm của học sinh đã xử lý trường hợp không có người trong thang một cách hợp lý, mặc dù không có đáp án cố định để so sánh.
- **cau_15__HS_10** / T15B1: text=`R1C1=8 | R1C2=32 | R2C1=3 người 5 người | R2C2=2 người 1 người | R3C1=8 | R3C2=23` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã đưa ra kết quả đúng cho 2 trường hợp trong 3 trường hợp được cung cấp, tuy nhiên chưa đưa ra thông tin cho trường hợp thứ hai.
- **cau_15__HS_10** / T15B2: text=`R1C1=8 | R1C2=32 | R2C1=3 người 5 người | R2C2=2 người 1 người | R3C1=8 | R3C2=23` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã đưa ra đúng đáp án cho hai bàn tròn trong hàng thứ nhất và hàng thứ ba, nhưng đáp án cho hai bàn tròn trong hàng thứ hai là sai.
- **cau_15__HS_10** / T15C2: text=`[box 1] Nhập N, M [box 2] int ngua = a, ngua = b [diamond 3] M % 2 == 0 [box 4] giải nih sai [box 5] N = a + b && M = 2 * a + 4 * b [box 6] xuất a, b [box 7] end 1 -> 2 2 -> 3 3 -> 4: True 3 -> 5: False 5 -> 6 6 -> 7 4 -> 7` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.2/0.2
  - LLM: Học sinh đã xác định đúng điều kiện 'giả định sai' dựa trên các điều kiện đã cho.
- **cau_3_001__HS_12** / T3: text=`a = 7 27` | expected=`None` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh chỉ sai 2 số trong đáp án, đáp ứng được 50% tiêu chí.
- **cau_5_001__HS_12** / T5: text=`10 3 1` | expected=`10 5 5` | heuristic=0.1667 (1/3 tokens correct (partial credit applied).) -> llm=0.25/0.5
  - LLM: Học sinh đã đúng một con số, đủ điều kiện để nhận 0.25 điểm theo tiêu chí.
- **cau_13__HS_12** / T13B: text=`void Tinhtong(int a[], int n) {
int main()
{
  int a[MAX], n=0;
  NhapMang(a,n);` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.0/0.5
  - LLM: Học sinh chưa thực hiện việc tìm vị trí phần tử có giá trị lớn nhất đầu tiên trong mảng theo yêu cầu.
- **cau_14__HS_12** / T14A: text=`struct SinhVien; char MasV; char HoTen; int NamSinh; char NgiSinh;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã sử dụng đúng tên và kiểu dữ liệu cho ba thuộc tính, nhưng lại bỏ qua hai thuộc tính khác.
- **cau_8__HS_15** / T8B: text=`0x505294 8 0 -2` | expected=`None` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được yêu cầu tối thiểu với 2 số đúng trong 3 số.
- **cau_10_001__HS_15** / T10: text=`10 70 23445217` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.1 (2/10 tokens correct (partial credit applied).) -> llm=0.5/0.5
  - LLM: Học sinh đáp ứng tiêu chí chính và được điểm bán phần theo quy tắc đã cho, tuy nhiên chưa có lời giải thích về lỗi (nếu có).
- **cau_11_001__HS_15** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_15** / T13B: text=`int max = 0; for (int i = 0; i < n; i++) {     if (a[i] == max) {         return i;     }     if (a[i] > max) {         max = a[i];         index = i;     } }` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh đáp ứng được tiêu chí tìm vị trí phần tử có giá trị lớn nhất ĐẦU TIÊN trong mảng theo yêu cầu của giáo viên.
- **cau_13__HS_15** / T13C2: text=`int main() { int a[MAY], n=0; NhapMang(a,n); cout << "Tong cac so nguyen to trong mang:" << Tong(a,n) << endl; cout << "Vi tri lon nhat dau tien:" << TimViTri(a,n) << endl; return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện một số yêu cầu khác ngoài tiêu chí TimMax(a,n).
- **cau_14__HS_15** / T14A: text=`struct SinhVien { char MaSV[100]; char HoTen[100]; int NamSinh; char NoiSinh[100];` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã sử dụng struct Sinhvien và khai báo các thuộc tính với đúng tên và kiểu dữ liệu như yêu cầu.
- **cau_14__HS_15** / T14B2: text=`void NhapSV(SinhVien a) { cin.getline(a.MaSV,100); cin.getline(a.NoiSinh,100); cin>>a.NamSinh; cin.ignore(); cin.getline(a.NoiSinh,100); cin.ignore();` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã sử dụng hàm getline đúng cách cho hai biến MaSV và NoiSinh, nhưng lại vi phạm tiêu chí khi sử dụng cin>> cho ngày sinh.
- **cau_14__HS_15** / T14C: text=`void InDSSV(Sinhvien a[], int n) { for(int i=0; i<n; i++) { cout << a[i].NoiSinh << "TPHCM"; cout << a[i].MaSV; cout << a[i].HoTen; cout << a[i].NamSinh; cout << a[i].NoiSinh; cout << a[i].DTB << endl;` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng yêu cầu in ra thông tin sinh viên có NoiSinh là 'TPHCM'.
- **cau_13__HS_17** / T13B: text=`int find(int a[], int &n) int ma = a[0]; int skibidi = 0; for(int i = 0; i < n; i++) {   if(a[i] > ma) skibidi = i;` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã đáp ứng được tiêu chí tìm vị trí phần tử có giá trị lớn nhất đầu tiên trong mảng.
- **cau_13__HS_17** / T13C2: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout << tong(a,n) << " " << find(a,n); return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã gọi hàm đúng tên và in kết quả ra màn hình, tuy nhiên không đủ thông tin để biết chắc chắn họ đã thực hiện đúng chức năng TimMax(a,n).
- **cau_14__HS_17** / T14A: text=`struct Sinh vien; String MaSV; Hoten; Nai Sinh; int Nam Sinh; float DTB;` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã làm đúng theo yêu cầu về khai báo struct Sinhvien với đúng tên và kiểu dữ liệu các thuộc tính, đồng thời đáp ứng được hướng dẫn của giáo viên về dấu chấm phẩy.
- **cau_14__HS_17** / T14C: text=`void InDSSV(Sinhvien a[], int n) { for (int i=0; i<n; i++) if (a[i].NoiSinh == "TPHCM") cout << a[i].MaSV << " " << a[i].HoTen << " " << a[i].NamSinh << " " << a[i].NoiSinh << " " << a[i].DTB << endl;` | expected=`None` | heuristic=0.125 (2/4 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được tiêu chí in thông tin sinh viên có NoiSinh là 'TPHCM' một cách chính xác.
- **cau_10_001__HS_18** / T10: text=`0 -1 2 -1 4 -1` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.1 (2/10 tokens correct (partial credit applied).) -> llm=0.0/0.5
  - LLM: Học sinh không đáp ứng được tiêu chí chính và không đủ điều kiện để nhận điểm bán phần hoặc điểm phụ theo quy định.
- **cau_14__HS_18** / T14A: text=`Abstract Sinh vien d. string NAM V.I. string Ho Ten; int Nam Sinh; string NAM V.I; float DTB;` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã cố gắng khai báo struct Sinhvien với các thuộc tính cần thiết nhưng chưa đáp ứng đúng tiêu chí về tên và kiểu dữ liệu các thuộc tính.
- **cau_14__HS_18** / T14B2: text=`void NhapSV(string &ten, string &maSV) { getLine(a.MaSV); getLine(a.NoiSinh); cin>>a.NamSinh; cin.ignore(100,'\n'); getLine(a.NoiSinh); cin>>a.DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đáp ứng đúng 2/4 tiêu chí yêu cầu, sử dụng getline cho 2 trường hợp. Tuy nhiên, việc sử dụng cin>> cho ten và DTB là sai, vi phạm tiêu chí.
- **cau_14__HS_18** / T14C: text=`void InDSSV(Sinhvien a[], int n) { for(int i=0; i<n; i++) { if(a[i].TenSV == 'TPTC') { count = a[i].NamSinh; count < a[i].NamSinh; count < a[i].NamSinh; count << a[i].DTB; }` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh chưa đáp ứng được tiêu chí yêu cầu. Họ đã định nghĩa hàm đúng và sử dụng vòng lặp for, nhưng chưa kiểm tra và in thông tin sinh viên có NoiSinh là 'TPHCM' đúng cách.
- **cau_15__HS_18** / T15A2: text=`int nattia() int a la Taji 8 dou cout << "la xua ra so con nguia"` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.125/0.125
  - LLM: Học sinh chưa đáp ứng được tiêu chí output theo yêu cầu, cần cải thiện phần output để đạt được điểm số cao hơn.
- **cau_3_001__HS_19** / T3: text=`a = 17` | expected=`None` | heuristic=0.0 (No output token correct.) -> llm=0.25/0.5
  - LLM: Học sinh đã đưa ra đáp án không chứa 4 số như tiêu chí yêu cầu, nhưng đáp án của họ đủ điều kiện nhận 0.25 điểm theo quy tắc điểm bán phần.
- **cau_13__HS_19** / T13A1: text=`bool kmaSNT(int x) { if (x < 2) return false; for (int i = 2; i < x / 2; i++) { if (x % i == 0) return false; return true; } int tang(int a[], int n) { int s = 0;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.5
  - LLM: Học sinh đã đáp ứng được 2/3 yêu cầu của tiêu chí KiemtraSNT, tuy nhiên chưa kiểm tra điều kiện quan trọng khi tìm được ước số.
- **cau_13__HS_19** / T13B: text=`int max_val = a[0]; for(int i = 0; i < n; i++) if (a[i] > a[0])` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.4/0.5
  - LLM: Học sinh đã sử dụng vòng lặp for và lệnh if để so sánh giá trị, tuy nhiên vẫn còn sai sót trong điều kiện so sánh.
- **cau_13__HS_19** / T13C1: text=`int main() { int a[MAX], n=0; NhapMang(a,n); for(int i=0; i<=n; i++) cout << "Taj la: " << taj(a,n); cout << "GTNN la: " << GTNN(a,n); return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã viết đúng hàm tính tổng các số nguyên tố nhưng đã sai về tên hàm và in thêm kết quả không cần thiết.
- **cau_13__HS_19** / T13C2: text=`int main() { int a[MAX], n=0; NhapMang(a,n); for(int i=0; i<=n; i++) cout << "Taj la: " << taj(a,n); cout << "GTNN la: " << GTNN(a,n); return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng yêu cầu tìm giá trị lớn nhất và in ra kết quả, tuy nhiên chưa cung cấp hàm TimMax(a, n như yêu cầu.
- **cau_14__HS_19** / T14A: text=`#include <iostream> #include <string> using namespace std; struct SinhVien {     string MaSV, HoTen, NoiSinh;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được 3/4 tiêu chí, tuy nhiên thiếu thuộc tính NamSinh. Điểm được tính là 0.8/1 nhưng giảm 0.1 để tuân thủ quy tắc chấm điểm.
- **cau_14__HS_19** / T14B1: text=`void NhapSV(Sinhvien &s getline(cin, s.HoTen); getline(cin, s.MaSV); getline(cin, s.NamSinh); getline(cin, s.Noisinh); cin >> s.DTB;` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh chưa đáp ứng được tiêu chí về việc truyền tham số đúng cho hàm NhapSV, do đó không nhận được điểm cho tiêu chí này.
- **cau_14__HS_19** / T14B2: text=`void NhapSV(Sinhvien &s getline(cin, s.HoTen); getline(cin, s.MaSV); getline(cin, s.NamSinh); getline(cin, s.Noisinh); cin >> s.DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.15/0.25
  - LLM: Học sinh đã sử dụng getline() để nhập các thông tin có khoảng trắng nhưng lại sử dụng cin>> để nhập thông tin điểm trung bình, không đáp ứng được tiêu chí.
- **cau_14__HS_19** / T14C: text=`void InDSSV(Sinhvien a[], int n) { for(int i = 0; i < n; i++) { if (s.NoiSinh == "TP HCM") { cout << s.MaSV << " " << s.HoTen << " " << s.NoiSinh << " " << s.Noi }` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được tiêu chí yêu cầu bằng cách in thông tin sinh viên có NoiSinh là 'TPHCM'.
- **cau_15__HS_19** / T15C2: text=`Input: So' nguoi: x, y
Kieu so' nguyen: x, y, M, N` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.2/0.2
  - LLM: Học sinh đã nỗ lực đưa ra các điều kiện giả định sai nhưng chưa chứng minh chúng là đúng.
- **cau_10_001__HS_21** / T10: text=`4 2 10 4 5 6 70 3 2 1` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.1 (2/10 tokens correct (partial credit applied).) -> llm=0.2/0.5
  - LLM: Học sinh đã trả lời đúng 2/10 câu hỏi, nhưng không có tiêu chí rõ ràng về việc phân ban phần điểm, do đó không thể đưa ra quyết định về điểm số cuối cùng dựa trên phân tích trên.
- **cau_11_001__HS_21** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_21** / T13A2: text=`bool ktraSNT(int n) { if(n<2){ return 0; } for(int i=0;i<n;i++) return 1; return 0; } int Tong(int a[],int n) { Sum=0 While(ktraSNT){` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.2/0.5
  - LLM: Học sinh đã nỗ lực định nghĩa hàm kiểm tra số nguyên tố nhưng chưa sử dụng đúng trong hàm tính tổng.
- **cau_13__HS_21** / T13C1: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout << Tong(a,n) << endl; cout << "Tổng giá trị các số nguyên tố:" << Tong(a,n) << endl; cout << "Vị trí phần tử có giá trị lớn nhất:" << Tong(a,n) << endl; return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện hầu hết các yêu cầu theo tiêu chí chấm thi, nhưng sử dụng hàm Tong(a,n) để tính cả tổng các số nguyên tố và vị trí phần tử có giá trị lớn nhất, thay vì sử dụng các hàm riêng biệt như yêu cầu.
- **cau_13__HS_21** / T13C2: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout << Tong(a,n) << endl; cout << "Tổng giá trị các số nguyên tố:" << Tong(a,n) << endl; cout << "Vị trí phần tử có giá trị lớn nhất:" << Tong(a,n) << endl; return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng yêu cầu chính về việc gọi hàm TimMax(a,n) và in kết quả. Tuy nhiên, sử dụng hàm Tong(a,n) để in thông tin không cần thiết làm mất tập trung.
- **cau_14__HS_21** / T14A: text=`#include <iostream> using namespace std; Struct SinhVien { String MaSV; HoTen; NaiSinh; int NamSinh; float DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã khai báo struct Sinhvien với đúng tên và kiểu dữ liệu các thuộc tính, tuy nhiên sử dụng từ 'NoiSinh' thay vì 'NaiSinh' như đề yêu cầu.
- **cau_14__HS_21** / T14C: text=`for (int i=0; i<n; i++) { if (a[i].NaiSanh == "TP.HCM") { cout << Sinhvien.a[i];` | expected=`None` | heuristic=0.0 (0/4 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng việc in thông tin sinh viên có NoiSinh là 'TPHCM' nhưng lại in cả thông tin khác cùng với NoiSinh.
- **cau_15__HS_21** / T15A2: text=`R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.0625/0.125
  - LLM: Học sinh đáp ứng yêu cầu nhất quán với câu c khi chọn không âm nhưng không đáp ứng đầy đủ khi chọn dương.
- **cau_15__HS_21** / T15C1: text=`R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh chưa đáp ứng đầy đủ tiêu chí, nhưng có thể nhận được 0.1 điểm nếu chỉ đưa ra một trong hai phương trình X + Y = N hoặc 2X + 4Y = M.
- **cau_15__HS_21** / T15C4: text=`R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng đúng công thức tính số ngựa Y theo tiêu chí chấm thi, dù đã sử dụng ký hiệu biến khác.
- **cau_13__HS_24** / T13A1: text=`bool isPrime(int n) { if (n < 2) return 0; for (int i = 0; i <= n; i++) if (n % i == 0) return 0; return 1; } int TongPrime(int a[], int n) { int s = 0; for (int i = 0; i < n; i++) if (isPrime(a[i])) s += a[i]; return s; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã cung cấp hàm isPrime đúng với tiêu chí yêu cầu, kiểm tra số nguyên tố một cách chính xác.
- **cau_13__HS_24** / T13A2: text=`bool isPrime(int n) { if (n < 2) return 0; for (int i = 0; i <= n; i++) if (n % i == 0) return 0; return 1; } int TongPrime(int a[], int n) { int s = 0; for (int i = 0; i < n; i++) if (isPrime(a[i])) s += a[i]; return s; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã sử dụng hàm isPrime đúng cách và tính tổng các số nguyên tố trong mảng a, đáp ứng đầy đủ tiêu chí chấm thi.
- **cau_13__HS_24** / T13C1: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout << TongPrime(a,n) << endl; cout << Viti(a,n); return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện hầu hết các yêu cầu của tiêu chí, tuy nhiên có một số sai sót nhỏ như tên hàm không khớp.
- **cau_13__HS_24** / T13C2: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout << TongPrime(a,n) << endl; cout << Viti(a,n); return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã gọi hàm TimMax(a,n) và in kết quả, đáp ứng một phần tiêu chí. Tuy nhiên, chức năng của các hàm khác không rõ ràng.
- **cau_14__HS_24** / T14A: text=`struct Sinhvien { string Masv; string HoTen, NoiSinh; int NamSinh; float DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã khai báo struct Sinhvien với đúng tên và kiểu dữ liệu các thuộc tính, tuy nhiên thiếu dấu chấm phẩy (;) sau thuộc tính cuối cùng.
- **cau_14__HS_24** / T14B2: text=`void NhapSV(Sinhvien &x) { gets(x.MaSV); gets(x.HoTen); cin >> x.NamSinh; gets(x.NoiSinh); cin >> x.DTB;` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.1875/0.25
  - LLM: Học sinh đã đáp ứng một phần yêu cầu khi sử dụng gets cho họ tên và nơi sinh, nhưng lại sử dụng cin >> cho ngày sinh, không đáp ứng được tiêu chí hoàn toàn.
- **cau_14__HS_24** / T14C: text=`void InDSSV(Sinhvien a[], int n) { Sinhvien x; for(int i=0; i<n; i++) if(strcmp(a[i].NamSinh, "TPHCM") == 0) { cout << a[i].Masv; puts(a[i].Hoten); cout << a[i].NamSinh << puts(a[i].NamSinh); cout << a[i].DTB; }` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.2/0.25
  - LLM: Học sinh đáp ứng được tiêu chí in thông tin sinh viên có NoiSinh là 'TPHCM' nhưng không tuân theo hướng dẫn của giáo viên về chỉ cần in đủ thông tin mà không cần in lặp lại thông tin không cần thiết.
- **cau_15__HS_24** / T15A2: text=`R1C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.125/0.125
  - LLM: Học sinh đã đáp ứng đúng tiêu chí output là chuỗi 'giả định sai'.
- **cau_15__HS_24** / T15B1: text=`R1C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.05/0.0833
  - LLM: Học sinh đã đưa ra giả định sai nhưng có thể sử dụng phương pháp đúng. Tuy nhiên, thiếu thông tin về quá trình giải nên không thể đưa ra quyết định chính xác.
- **cau_15__HS_24** / T15B3: text=`R1C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R3.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã đưa ra kết quả chính xác 'giả định sai' cho input 9 10, khớp với tiêu chí chấm thi và đáp án kỳ vọng.
- **cau_15__HS_24** / T15C4: text=`R1C2=giả định sai` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng công thức tính số ngựa Y đúng theo tiêu chí đề ra, mặc dù sử dụng ký hiệu biến khác.
- **cau_11_001__HS_26** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_26** / T13A1: text=`bool isprime(int x) for(int i=2; i<=x; i++) if(x%i==0) bool isprime(int x) if(x==1 || x==2) return false; for(int i=2; i<=x; i++) if(x%i==0) return false; return true;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.5
  - LLM: Học sinh đã nắm được cơ bản về việc kiểm tra số nguyên tố nhưng vẫn còn thiếu một số trường hợp đặc biệt.
- **cau_13__HS_26** / T13B: text=`int ViTri(int a[], int n) int max1 = a[0]; cnt = 0; return cnt; for(int i = 1; i < n; i++) if(a[i] > max1)` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.0/0.5
  - LLM: Học sinh chưa hoàn thành việc tìm vị trí phần tử có giá trị lớn nhất theo tiêu chí yêu cầu và cũng không đáp ứng được ghi chú của giáo viên.
- **cau_13__HS_26** / T13C1: text=`int main() {     int a[MAX], n=0;     NhapMang(a,n);     cout << Tong(a,n);     cout << VTri(a,n);     return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng yêu cầu chính của bài toán, tuy nhiên còn gọi thêm một hàm không cần thiết.
- **cau_14__HS_26** / T14A: text=`Struct SinhVien char MaSV; char HoTen; int NamSinh; char NoiSinh;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã khai báo struct Sinhvien với đúng tên và kiểu dữ liệu các thuộc tính như yêu cầu.
- **cau_14__HS_26** / T14B1: text=`void NhapSV(...SinhVien a[]) {     cin >> MasVi;     cin.ignore();     cin >> HoTen;     cin >> NamSinh >> NoiSinh >> DTB;` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh đã truyền tham trị thay vì tham chiếu, không đáp ứng được tiêu chí.
- **cau_15__HS_26** / T15B1: text=`R1C1=2 6 | R1C2=1 1 | R2C1=3 10 | R2C2=1 2 | R3C1=3 11 | R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R1.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã làm đúng 4/6 phần tử theo tiêu chí đề ra. Tuy nhiên, phần tử R3C2 sai nên không đáp ứng được yêu cầu.
- **cau_15__HS_26** / T15B3: text=`R1C1=2 6 | R1C2=1 1 | R2C1=3 10 | R2C2=1 2 | R3C1=3 11 | R3C2=giả định sai` | expected=`None` | heuristic=0.0417 (1/2 expected values found at row R3.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã áp dụng đúng công thức tính giá trị cho hầu hết các trường hợp và nhận biết được trường hợp giả định sai.
- **cau_15__HS_26** / T15C1: text=`[circle 1] bát trai [box 2] Nhập M, N [box 3] giải hệ 1 -> 2 2 -> 3` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã đáp ứng được tiêu chí đưa ra hệ phương trình X+Y=N, 2X+4Y=M.
- **cau_15__HS_26** / T15C4: text=`[circle 1] bát trai [box 2] Nhập M, N [box 3] giải hệ 1 -> 2 2 -> 3` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã thực hiện hai bước trong ba bước yêu cầu, bao gồm nhập M, N và giải hệ 1 -> 2, 2 -> 3. Tuy nhiên, họ chưa tính số ngựa Y theo công thức Y = M/2 - N.
- **cau_10_001__HS_28** / T10: text=`9 10 1 2 3 4 5 9 7 0 1 2 3 4 5 6 7` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.1 (2/10 tokens correct (partial credit applied).) -> llm=0.0/0.5
  - LLM: Bài làm của học sinh có nhiều chỗ sai, chỉ có 2/10 token khớp với đáp án đúng. Không có thông tin về lỗi runtime error hoặc bị lỗi, không đủ điều kiện để cộng 0.5 điểm theo quy tắc ghi chú của giáo viên.
- **cau_13__HS_28** / T13A2: text=`void TinhTongSnt(int a[], int &n)` | expected=`None` | heuristic=0.25 (1/2 expected values found.) -> llm=0.45/0.5
  - LLM: Học sinh đã thực hiện đúng yêu cầu của hàm nhưng có thể chưa kiểm tra kỹ điều kiện số nguyên tố.
- **cau_13__HS_28** / T13B: text=`void TinhTongSnt(int a[], int &n)
int main()
{
    int a[MAX], n=0;
    NhapMang(a,n);` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.0/0.5
  - LLM: Học sinh chưa thực hiện đúng yêu cầu tìm vị trí phần tử có giá trị lớn nhất đầu tiên theo tiêu chí chấm thi.
- **cau_13__HS_29** / T13A1: text=`int TongSNTto bool cnqt(int n) if (n <= 2) return 0; for (int i = 0; i <= n; i++) if (n % i == 0) return 0; return 1; int tong (int a[], int n) int sum = 0; for (int i = 0; i < n; i++) if (a[cnqt(a[i])] sum = sum + a[i]` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã hiểu và thực hiện đúng yêu cầu của tiêu chí, kiểm tra chính xác số nguyên tố và sử dụng hàm này đúng cách trong hàm tổng cộng các số nguyên tố.
- **cau_13__HS_29** / T13A2: text=`int TongSNTto bool cnqt(int n) if (n <= 2) return 0; for (int i = 0; i <= n; i++) if (n % i == 0) return 0; return 1; int tong (int a[], int n) int sum = 0; for (int i = 0; i < n; i++) if (a[cnqt(a[i])] sum = sum + a[i]` | expected=`None` | heuristic=0.25 (1/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã đáp ứng được yêu cầu của tiêu chí, tuy nhiên có một sai sót nhỏ trong cách sử dụng biến trong hàm `tong`.
- **cau_13__HS_29** / T13B: text=`for (int i = 0; i < n; i++) int Max = A[0]; if (A[i] == Max) for (int i = 1; i < n; i++) if (A[i] > Max)` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.0/0.5
  - LLM: Học sinh chưa đáp ứng được yêu cầu tìm vị trí phần tử có giá trị lớn nhất ĐẦU TIÊN. Việc tìm thấy 3/6 phần tử lớn nhất không đủ điều kiện để đạt điểm.
- **cau_13__HS_29** / T13C1: text=`int a[MAX], n=0; NhapMang(a,n); int k = tong(a,n); int v = CoViTri(a,n); cout << "tong so nguyen to trong mang la:" << k << endl; cout << "vi tri cua phan tu co gia tri lon nhat la:" << v;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng việc tìm vị trí phần tử có giá trị lớn nhất nhưng chưa đúng với yêu cầu về hàm `TongSNT(a,n)`. Học sinh đã gọi hàm `tong(a,n)` để tính tổng các phần tử trong mảng nhưng chưa tính tổng số nguyên tố.
- **cau_14__HS_29** / T14A: text=`char Sinh nien; char MaSV[10]; char HoTen[10]; int NamSinh; char NolSinh[10]; float DTB;` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã sử dụng đúng tên và kiểu dữ liệu của các thuộc tính trong struct Sinhvien, tuy nhiên họ đã bỏ qua dấu chấm phẩy sau dấu } đóng struct.
- **cau_10_001__HS_30** / T10: text=`70 1 2 3 4 5 6 7 8` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.15 (3/10 tokens correct (partial credit applied).) -> llm=0.25/0.5
  - LLM: Học sinh chỉ đúng 2/10 vị trí, phần lớn là sai. Tuy nhiên, áp dụng quy tắc điểm bán phần.
- **cau_11_001__HS_30** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_30** / T13A1: text=`bool SNT(int a) { if(a<02) return 1; for(int i=2;i<n;i++) if(n%i==0) return 0; return 1; } int Tong(int a[], int n) { int dem=0; for(int i=0;i<n;i++) if(SNT(a[i])) dem = dem + a[i];` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã viết đúng hàm kiểm tra số nguyên tố nhưng đã sai khi tính tổng các số nguyên tố trong mảng.
- **cau_13__HS_30** / T13A2: text=`bool SNT(int a) { if(a<02) return 1; for(int i=2;i<n;i++) if(n%i==0) return 0; return 1; } int Tong(int a[], int n) { int dem=0; for(int i=0;i<n;i++) if(SNT(a[i])) dem = dem + a[i];` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.5
  - LLM: Học sinh đã implement được hàm SNT và sử dụng nó trong hàm Tong. Tuy nhiên, họ chưa đáp ứng được yêu cầu chính của tiêu chí (tính tổng các số nguyên tố).
- **cau_13__HS_30** / T13B: text=`for(int i=0; i<n; i++) int m = a[0]; for(int i=0; i<n; i++) if(m < a[i]) m = a[i]; for(int i=0; i<n; i++)` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã đáp ứng được yêu cầu tìm phần tử có giá trị lớn nhất nhưng chưa đáp ứng được yêu cầu in ra vị trí của phần tử này.
- **cau_14__HS_30** / T14A: text=`Struct SinhVien; char MSV[1]; char HoTen[1]; int NamSinh; char NoiSinh[1];` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.2/0.25
  - LLM: Học sinh đã khai báo struct SinhVien với đúng tên và kiểu dữ liệu cho hầu hết các thuộc tính, tuy nhiên quên khai báo thuộc tính DTB.
- **cau_14__HS_30** / T14B1: text=`void NhapSV(Sinhvien &a)` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh đã sử dụng tham trị để truyền đối tượng Sinhvien vào hàm NhapSV, tuy nhiên chưa đáp ứng được yêu cầu sử dụng tham chiếu &x.
- **cau_14__HS_30** / T14C: text=`for(int i=0;i<n;i++) if(a.NoiSinh=="TPHCM") cout<<a.MasV<<a.HoTen<<a.NamSinh<<a.NoiSinh<<a.DTB; else Continue;` | expected=`None` | heuristic=0.0 (0/4 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng được yêu cầu in thông tin sinh viên có NoiSinh là 'TPHCM'.
- **cau_11_001__HS_32** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_32** / T13B: text=`int mean(){
int Sum = 0
for (i = int i = 0; i < n; i++)
if (a[i] % 10 == 0 && a[i] % 100 == 0)
Sum += a[i];
return Sum;
int sum = 0;
cout << "Tong gia tri cac so nguyen to = " << sum;` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.0/0.5
  - LLM: Học sinh chưa đáp ứng được tiêu chí tìm vị trí phần tử có giá trị lớn nhất ĐẦU TIÊN.
- **cau_14__HS_32** / T14B1: text=`void NhapSV(...) cin >> a[i].MaSV; cin >> a[i].HoTen; cin >> a[i].NamSinh;` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh chưa đáp ứng được yêu cầu về việc truyền tham số Sinhvien &x vào hàm.
- **cau_10_001__HS_34** / T10: text=`10 1 2 2 3 4 5 6 7` | expected=`10 70 2 3 4 4 5 6 2 1` | heuristic=0.25 (5/10 tokens correct (partial credit applied).) -> llm=0.5/0.5
  - LLM: Học sinh đã đúng một nửa đáp án và có 3 sai lầm nghiêm trọng, nhưng không bỏ qua bất kỳ đáp án nào. Tuy nhiên, cần kiểm tra bài làm của học sinh xem họ có giải thích đúng về lỗi không.
- **cau_11_001__HS_34** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_34** / T13A1: text=`bool Songto(int n) { if(n<2) return false; for(int i=2; i<= n/2; i++) { if(n%i==0) return false; } return true; } int Tinh(int a[], int n) { int s = 0; for(int i=0; i<n; i++)` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.4/0.5
  - LLM: Học sinh đã định nghĩa hàm kiểm tra số nguyên tố đúng cách, sử dụng lặp for để kiểm tra chia hết từ 2 đến n/2. Tuy nhiên, tiêu chí không nêu rõ việc kiểm tra đối với các số lớn hơn 2^31 - 1 (giống như trong bài làm).
- **cau_13__HS_34** / T13B: text=`int lim(int a[], int n) { int max = a[0]; for (int i = 1; i <= n; i++) if (max < a[i]) max = a[i];` | expected=`None` | heuristic=0.25 (3/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã tìm vị trí phần tử có giá trị lớn nhất đầu tiên, tuy nhiên tiêu chí đề 1 tìm max, đề 2 tìm min chưa được nêu rõ trong bài làm.
- **cau_13__HS_34** / T13C1: text=`int main() { int a[MAX], n=0; NhapMang(a,n); cout << Tinh(a,n); cout << Tim(a,n); return 0; }` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng yêu cầu về tính tổng các số nguyên tố nhưng chưa đạt được 0.25 điểm do chưa in kết quả ra màn hình.
- **cau_14__HS_34** / T14A: text=`Slauct Sinhvien; Chan MasV; Chan HoTen; int NamSinh; chan Noi Sinh;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.0833/0.25
  - LLM: Học sinh chỉ thực hiện đúng 1/3 yêu cầu, cụ thể là khai báo thuộc tính NamSinh với kiểu int. Các thuộc tính khác đều sai về chính tả, cấu trúc và dấu chấm phẩy.
- **cau_14__HS_34** / T14B2: text=`void NhapSV(Sinhvien &x) cin.getline(x.MaSV); cin.getline(x.HoTen); cin>>x.NamSinh; cin.getline(x.NoiSinh); cin>>x.DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.1667/0.25
  - LLM: Học sinh đã thực hiện đúng tiêu chí ở 2/3 trường hợp (mã sinh viên, họ tên, nơi sinh), sai ở 1/3 trường hợp (năm sinh).
- **cau_14__HS_34** / T14C: text=`void InDSSV(Sinhvien a[], int n) { if(x.NoiSinh == 'TPHCM') Coat <= x` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh đã kiểm tra điều kiện đúng nhưng không thực hiện việc in thông tin sinh viên như yêu cầu.
- **cau_15__HS_34** / T15A1: text=`int N; // Tăng ceng do dau int M; // Teng ceng do chăn input la 2 so nguyen voi M > N > 2 output la 2 so nguyen la so nguyen va so ng` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.125/0.125
  - LLM: Học sinh đã đáp ứng đầy đủ các yêu cầu về input và output đã nêu.
- **cau_15__HS_34** / T15B2: text=`R1C1=3 | R1C2=8 | R2C1=2 | R2C2=1 | R3C1=5 | R3C2=16 | R4C1=2 | R4C2=3 | R5C1=5 | R5C2=8` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã thực hiện đúng yêu cầu của bài toán cho cả 10 cặp số nguyên được cung cấp, đáp ứng đầy đủ tiêu chí chấm thi.
- **cau_15__HS_34** / T15C3: text=`int N; // Tăng ceng do dau
int M; // Teng ceng do chăn
input la 2 so nguyen voi M > N > 2
output la 2 so nguyen la so nguyen va so ng` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã áp dụng đúng công thức tính số người nhưng chưa in ra kết quả.
- **cau_11_001__HS_36** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_36** / T13A1: text=`int tongsnT(int a[], int n) int S = 0; for (int i = 0; i < n; i++)   for (int j = 0; j * j <= a[i]; j++)     if (a[i] % j == 0)       break;     if (j * j == a[i])       S++` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã sử dụng đúng logic để kiểm tra số nguyên tố, tuy nhiên họ quên kiểm tra trường hợp đặc biệt cho số 1 và số 2.
- **cau_13__HS_36** / T13A2: text=`int tongsnT(int a[], int n) int S = 0; for (int i = 0; i < n; i++)   for (int j = 0; j * j <= a[i]; j++)     if (a[i] % j == 0)       break;     if (j * j == a[i])       S++` | expected=`None` | heuristic=0.25 (1/2 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã thực hiện đúng yêu cầu của tiêu chí chấm thi, tính tổng số nguyên tố trong mảng.
- **cau_13__HS_36** / T13B: text=`for (int i = 0; i < n; i++) s = a[i]; if (a[i] < a[i+1])` | expected=`None` | heuristic=0.1667 (2/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã sử dụng vòng lặp for và so sánh giá trị các phần tử, tuy nhiên họ sử dụng sai toán tử trong if statement, dẫn đến việc tìm kiếm phần tử không đúng. Tuy nhiên, tiêu chí chấm thi chỉ yêu cầu tìm vị trí phần tử có giá trị lớn nhất ĐẦU TIÊN, không yêu cầu tìm cả giá trị đó.
- **cau_13__HS_36** / T13C1: text=`int a[MAX], n=0; NhapMang(a,n); cout << tongstn(a,n); cout << solonnhat(a,n); return 0;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng yêu cầu về việc in ra tổng các số nguyên tố và số nguyên tố lớn nhất, tuy nhiên chưa định nghĩa và thực hiện hàm `TongSNT(a,n)` như yêu cầu.
- **cau_14__HS_36** / T14A: text=`struct SinhVien { int NamSinh; char MaSV, HoTen, NoiSinh; float DTB;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.0/0.25
  - LLM: Không đáp ứng đủ các tiêu chí yêu cầu, thiếu dấu chấm phẩy sau dấu } đóng struct và có sai sót về thứ tự và kiểu dữ liệu các thuộc tính.
- **cau_14__HS_36** / T14B1: text=`void NhapSV(Sinhvien &a) { cin>>a.NamSinh; cin>>a.DTB; cin.ignore(); cin.getline(a.MSSV,100); cin.getline(a.HoTen,100); cin.getline(a.NoiSinh,100);` | expected=`None` | heuristic=0.125 (1/2 expected values found.) -> llm=0.0/0.25
  - LLM: Học sinh đã vi phạm yêu cầu truyền tham trị bởi họ đã sửa đổi giá trị của đối tượng bên trong hàm.
- **cau_14__HS_36** / T14C: text=`void InDSSV(Sinhvien a[], int n)` | expected=`None` | heuristic=0.0625 (1/4 expected values found.) -> llm=0.1875/0.25
  - LLM: Học sinh đã đáp ứng được 3/4 yêu cầu của tiêu chí, nên họ đáng được điểm 3/4 trong tiêu chí này.
- **cau_15__HS_36** / T15B2: text=`R1C1=Số đầu: 1
Số chẵn: 2 | R1C2=1 người, 0 người | R2C1=Số đầu: 2
Số chẵn: 2 | R2C2=2 người, 1 người | R3C1=Số đầu: -1
Số chẵn: 1,3 | R3C2=giả định sai` | expected=`None` | heuristic=0.0 (0/2 expected values found at row R2.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã nắm được cơ bản tiêu chí nhưng vẫn còn sai sót.
- **cau_15__HS_36** / T15B3: text=`R1C1=Số đầu: 1
Số chẵn: 2 | R1C2=1 người, 0 người | R2C1=Số đầu: 2
Số chẵn: 2 | R2C2=2 người, 1 người | R3C1=Số đầu: -1
Số chẵn: 1,3 | R3C2=giả định sai` | expected=`None` | heuristic=0.0417 (1/2 expected values found at row R3.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã đáp ứng được yêu cầu đưa ra giả định và in ra kết quả 'giả định sai' dựa trên số người là 1,3, mặc dù số đầu là -1 không hợp lý. Tuy nhiên, họ đã thực hiện đúng yêu cầu của tiêu chí.
- **cau_15__HS_36** / T15C1: text=`input: n cái đầu, m cái chân (n, m ∈ N)
output: có a người, b người` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.05/0.1
  - LLM: Học sinh đã đưa ra hệ phương trình tương tự như tiêu chí yêu cầu, tuy nhiên chưa giải thích rõ ràng về ý nghĩa của các biến trong bối cảnh vấn đề.
- **cau_15__HS_36** / T15C2: text=`input: n cái đầu, m cái chân (n, m ∈ N)
output: có a người, b người` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.2/0.2
  - LLM: Học sinh đã xác định đúng ít nhất một điều kiện 'giả định sai' theo yêu cầu của tiêu chí chấm điểm.
- **cau_15__HS_36** / T15C4: text=`input: n cái đầu, m cái chân (n, m ∈ N)
output: có a người, b người` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Bài làm đã sử dụng đúng công thức tính số ngựa, tuy nhiên chưa xét đến tất cả các trường hợp khả quan.
- **cau_11_001__HS_39** / T11: text=`20` | expected=`20` | heuristic=0.5 (Student answer matches accepted output (pre-check).) -> llm=0.5/0.5
  - LLM: Bài làm của học sinh cho ra kết quả giống đáp án kỳ vọng, tuy nhiên thiếu thông tin tiêu chí chấm thi cụ thể để đưa ra quyết định chính xác.
- **cau_13__HS_39** / T13B: text=`int LN = c[0]; int t; t = 0; for (int i = 0; i < n; i++) { if (c[i] > LN) { t = i; LN = c[i]; } }` | expected=`None` | heuristic=0.0833 (1/6 expected values found.) -> llm=0.5/0.5
  - LLM: Học sinh đã sử dụng đúng dấu > trong lệnh if, đáp ứng được tiêu chí tìm vị trí phần tử có giá trị lớn nhất đầu tiên.
- **cau_13__HS_39** / T13C1: text=`int a[MAX], n=0; NhapMang(a,n); cout << "Tong gia tri cua cac phan tu la: " << Tong(a,n); cout << "Vi tri cua phan tu co GTLN la: " << GTLN(a,n);` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã đáp ứng đầy đủ các tiêu chí chấm thi bằng cách viết hàm `TongSNT(a,n)` và `GTLN(a,n)` như yêu cầu, và in kết quả của cả hai hàm.
- **cau_14__HS_39** / T14A: text=`struct SinhVien {   string MaSV;   string HoTen;   int NamSinh;   string NoiSinh;` | expected=`None` | heuristic=0.0833 (1/3 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã thực hiện đúng 4/5 tiêu chí yêu cầu, tuy nhiên quên không khai báo thuộc tính DTB. Điểm dự kiến có thể điều chỉnh dựa trên hướng dẫn của giáo viên.
- **cau_14__HS_39** / T14B1: text=`struct SinhVien {
  string MaSV;
  string HoTen;
  int NamSinh;
  string NoiSinh;` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.25/0.25
  - LLM: Học sinh đã sử dụng '&' để truyền tham chiếu đối với đối tượng 'Sinhvien', đáp ứng được tiêu chí yêu cầu.
- **cau_15__HS_39** / T15A2: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.0625/0.125
  - LLM: Bài làm của học sinh không hoàn toàn khớp với tiêu chí chấm thi, nhưng có thể xem là đáp ứng một phần yêu cầu bởi nó có thể được xem là nhất quán với câu c khi chọn không âm.
- **cau_15__HS_39** / T15B1: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã đưa ra đáp án đúng nhưng thiếu thông tin về quá trình giải quyết vấn đề.
- **cau_15__HS_39** / T15B2: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.0833/0.0833
  - LLM: Học sinh đã đáp ứng đúng tiêu chí khi đưa ra output 0 5 cho input 5 20. Bài làm của học sinh khớp hoàn toàn với tiêu chí chấm thi.
- **cau_15__HS_39** / T15B3: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.0834/0.0834
  - LLM: Học sinh đã giải quyết đúng vấn đề với input 9 10 và output 'giả định sai'.
- **cau_15__HS_39** / T15C1: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/2 expected values found.) -> llm=0.08/0.1
  - LLM: Học sinh đã đưa ra hệ phương trình đúng nhưng thiếu thông tin về giá trị của N và M.
- **cau_15__HS_39** / T15C2: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/3 expected values found.) -> llm=0.2/0.2
  - LLM: Học sinh đã nỗ lực đưa ra hai điều kiện giả định sai, mặc dù chưa hoàn chỉnh và không nhất quán.
- **cau_15__HS_39** / T15C3: text=`a: ben chieu ng, b: la chieu ng` | expected=`None` | heuristic=0.0 (0/1 expected values found.) -> llm=0.1/0.1
  - LLM: Học sinh đã sử dụng đúng công thức X = 2*N - M/2 để tính số người cần đi chợ theo tiêu chí đã cho.
