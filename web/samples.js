// Sample briefs. "Demo" mixes every verdict; "Mata v. Avianca" rebuilds the citation list from the
// court's sanctions opinion (No. 22-cv-1461, S.D.N.Y. 2023); the surrounding text is ours.
window.REDLINE_SAMPLES = [
  {
    id: "demo",
    label: "Demo brief",
    text: `Defendant's motion should be denied. The Montreal Convention does not preempt Plaintiff's claim, and the limitations period was tolled. Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339, 1345 (11th Cir. 2019); Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999). The Convention is read by its text. Zicherman v. Korean Air Lines Co., 516 U.S. 217, 226 (1996).

The agency's reading of the regulation also deserves deference. Chevron U.S.A. Inc. v. Natural Resources Defense Council, Inc., 467 U.S. 837, 842-43 (1984). The Fifth Circuit applied that framework to the Clean Water Act. Southwestern Elec. Power Co. v. EPA, 920 F.3d 999, 1013 (5th Cir. 2019).

Finally, the D.C. Circuit's reasoning on access to medical care applies here. J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019). Illinois courts agree. Shaboon v. Egyptair, 2013 IL App (1st) 111279-U.`
  },
  {
    id: "agent",
    label: "Written by an AI",
    // Verbatim from briefs Claude Sonnet drafted in our agent experiment (bench/results/agent/memory/runs/
    // m02-A-2.json and m21-B-3.json; markdown removed). Both cases are real; both citations are wrong.
    text: "When the allegations, fairly read, describe only conduct or injury that the policy excludes, the complaint states no potentially covered claim and the duty to defend does not attach. See Mount Vernon Fire Ins. Co. v. Visionaid, Inc., 477 F.3d 6, 9\u201310 (1st Cir. 2007) (comparing the complaint's factual allegations to the policy and the exclusions at issue); Metro. Prop. & Cas. Ins. Co. v. Morrison, 460 F.3d 52, 58\u201359 (1st Cir. 2006) (same).\n\nThe Eleventh Circuit has also treated Montreal Convention questions under ordinary principles of treaty interpretation, giving effect to the text and to the forum-law references the drafters chose to include. See Campbell v. Air Jamaica Ltd., 863 F.3d 1255 (11th Cir. 2017)."
  },
  {
    id: "mata",
    label: "Mata v. Avianca (2023)",
    as_of: 2023,
    text: `Plaintiff's claims are not preempted, and the Montreal Convention's limitations period was tolled by Avianca's bankruptcy. See Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339, 1345 (11th Cir. 2019); Shaboon v. Egyptair, 2013 IL App (1st) 111279-U; Petersen v. Iran Air, 905 F. Supp. 2d 121 (D.D.C. 2012); Martinez v. Delta Airlines, Inc., 2019 WL 4639462 (Tex. App. Sept. 25, 2019); Estate of Durden v. KLM Royal Dutch Airlines, 2017 WL 2418825 (Ga. Ct. App. June 5, 2017); Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999).

The Convention is to be read according to its text. Zicherman v. Korean Air Lines Co., 516 U.S. 217, 226 (1996); El Al Israel Airlines, Ltd. v. Tsui Yuan Tseng, 525 U.S. 155 (1999).`
  },
  {
    id: "chevron",
    label: "Agency deference",
    text: `The agency's reading of the statute is entitled to deference. Under Chevron U.S.A. Inc. v. Natural Resources Defense Council, Inc., 467 U.S. 837, 842-43 (1984), a court asks first whether Congress has spoken to the precise question, and if not, whether the agency's answer is reasonable. Courts apply the same framework to an agency's reading of its own jurisdiction. City of Arlington v. FCC, 569 U.S. 290, 296 (2013). The Fifth Circuit has applied both steps to the Clean Water Act. Southwestern Elec. Power Co. v. EPA, 920 F.3d 999, 1013 (5th Cir. 2019). So has the Eleventh Circuit. Perez-Sanchez v. U.S. Att'y Gen., 935 F.3d 1148 (11th Cir. 2019).`
  },
  {
    id: "clean",
    label: "Clean brief",
    text: `A complaint must plead facts that make the claim plausible, not merely conceivable. Bell Atlantic Corp. v. Twombly, 550 U.S. 544, 570 (2007); Ashcroft v. Iqbal, 556 U.S. 662, 678 (2009). A party opposing summary judgment must point to specific facts. Celotex Corp. v. Catrett, 477 U.S. 317, 324 (1986). Expert testimony must rest on reliable methods. Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999).`
  }
];
