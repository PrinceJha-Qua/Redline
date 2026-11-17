CREATE FULLTEXT INDEX `case_name` FOR (n:`Case`) ON EACH [n.`name`] OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words',`fulltext.eventually_consistent`: false}};
CREATE RANGE INDEX `case_status` FOR (n:`Case`) ON (n.`status`);
CREATE CONSTRAINT `case_id` FOR (n:`Case`) REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `citation_text` FOR (n:`Citation`) REQUIRE (n.`text`) IS UNIQUE;
CREATE CONSTRAINT `court_id` FOR (n:`Court`) REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `reporter_abbr` FOR (n:`Reporter`) REQUIRE (n.`abbr`) IS UNIQUE;
CREATE CONSTRAINT `volume_key` FOR (n:`Volume`) REQUIRE (n.`key`) IS UNIQUE;
