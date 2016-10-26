$(function () {

	//Mostly copied from http://www.highcharts.com/stock/demo/lazy-loading

    function afterSetExtremes(e) {

        var chart = $('#container').highcharts();

        chart.showLoading('Fetching data...');

		// TODO
    	//$.getJSON('http://kahviraspi/getdata?=' + Math.round(e.min) + '&end=' + Math.round(e.max) + '&callback=?', function (data) {
    	//$.getJSON('http://kahvi.fyysikkokilta.fi/getdata.php?start=' + Math.round(e.min) + '&end=' + Math.round(e.max) + '&callback=?', function (data) { // callback needed?
        $.getJSON('https://www.highcharts.com/samples/data/from-sql.php?start=' + Math.round(e.min) +
                '&end=' + Math.round(e.max) + '&callback=?', function (data) {

			//TODO: two series
            chart.series[0].setData(data);
            chart.hideLoading();
        });
    }


 	//TODO: see https://github.com/highcharts/highcharts/blob/master/samples/data/from-sql.php on how to set up the queries for averaged data. most importantly:
	//TODO: also check out how meso does this and consider that as well
	/*
		// find the right table
		// two days range loads minute data
		if ($range < 2 * 24 * 3600 * 1000) {
			$table = 'stockquotes';
			
		// one month range loads hourly data
		} elseif ($range < 31 * 24 * 3600 * 1000) {
			$table = 'stockquotes_hour';
			
		// one year range loads daily data
		} elseif ($range < 15 * 31 * 24 * 3600 * 1000) {
			$table = 'stockquotes_day';
		// greater range loads monthly data
		} else {
			$table = 'stockquotes_month';
		} 
	 */
    $.getJSON('https://www.highcharts.com/samples/data/from-sql.php?callback=?', function (data) {

        // Add a null value for the end date
        //data = [].concat(data, [[Date.UTC(2014, 9, 14, 19, 59), null, null, null, null]]);

        // Create the chart
        $('#container').highcharts('StockChart', {


            title: {
                text: 'Kahvin määrä kiltiksellä ajan funktiona'
            },

            chart: {
                zoomType: 'x'
            },

            navigator: {
                adaptToUpdatedData: false,
                series: {
                    data: data
                }
            },

            scrollbar: {
                liveRedraw: false
            },

            rangeSelector: {
                buttons: [{
                    type: 'hour',
                    count: 1,
                    text: '1h'
                }, {
                    type: 'day',
                    count: 1,
                    text: '1d'
                },
				//TODO: week (?)
				{
                    type: 'month',
                    count: 1,
                    text: '1m'
                },
				//TODO: remove year?
				{
                    type: 'year',
                    count: 1,
                    text: '1y'
                }, {
                    type: 'all',
                    text: 'All'
                }],
                inputEnabled: false, // it supports only days
                selected: 4 // all
            },

            xAxis: {
                events: {
                    afterSetExtremes: afterSetExtremes
                },
				minRange: 60 * 1000 // one minute (TODO: increase? 10 minutes?)
            },

            yAxis: {
                floor: 0
            },

            series: [{
                name: 'kahvi',
                data: data,
                tooltip: {
                    valueDecimals: 2
                },
                dataGrouping: {
                    enabled: false
                }
            }]
        });
    });

});

